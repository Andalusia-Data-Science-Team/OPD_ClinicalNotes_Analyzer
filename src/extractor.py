"""
AI-powered clinical notes extractor. Department-agnostic: required fields,
field aliases, and prompts come from src.skill_loader based on config.department.
"""
import json
import re
import time
from typing import List, Dict, Optional
import os

# Conditional import for OpenAI (OpenRouter)
try:
    import openai
except ImportError:
    openai = None

# Fireworks fallback
try:
    from fireworks.client import Fireworks
except ImportError:
    Fireworks = None

from src.skill_loader import load_skill


class ClinicalNotesExtractor:
    """
    AI-powered clinical notes extractor supporting OpenRouter (OpenAI-compatible)
    and Fireworks API. Plugs in OPD or ER field schema + prompt via `department`.
    """
    def __init__(
        self,
        department: str,
        api_key: str = None,
        model: str = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        timeout: int = 120
    ):
        skill = load_skill(department)
        self.department = department.strip().upper()
        self.required_fields: List[str] = skill["required_fields"]
        self.field_aliases: Dict[str, str] = skill["field_aliases"]
        self.cached_system_prompt: str = skill["system_prompt"]
        self.get_user_prompt = skill["get_user_prompt"]
        self.scoring_fn = skill["scoring_fn"]

        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout

        # Cumulative token usage across all calls made by this extractor instance
        # (used by the Airflow DAG to compute per-run cost).
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("FIREWORKS_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL") or os.getenv("MODEL")

        self.use_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))
        self.use_fireworks = not self.use_openrouter

        if self.use_openrouter:
            if openai is None:
                raise ImportError("openai package is required for OpenRouter support. Please install openai.")
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1"
            )
        elif self.use_fireworks:
            if Fireworks is None:
                raise ImportError("fireworks.client is required for Fireworks support. Please install fireworks-ai.")
            self.client = Fireworks(api_key=self.api_key)

    def extract_features(
        self,
        notes: List[str],
        diagnosis_context: Optional[List[Dict]] = None,
        retry_count: int = 0
    ) -> List[Dict]:
        """Extract structured features from clinical notes with retry logic."""
        try:
            if not notes:
                raise ValueError("Notes list cannot be empty")

            user_prompt = self.get_user_prompt(notes, diagnosis_context=diagnosis_context)

            input_token_estimate = len(user_prompt) // 4
            output_token_estimate = max(6000, len(notes) * 1500)
            max_tokens = min(32_768, output_token_estimate)
            if input_token_estimate > 20_000:
                print(f"   WARNING: large batch (~{input_token_estimate} input tokens). "
                      f"Consider reducing batch_size in .env to avoid truncation.")

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.cached_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )

            processing_time = time.time() - start_time

            usage = getattr(response, 'usage', None)
            if usage:
                in_tok = getattr(usage, 'prompt_tokens', None) or 0
                out_tok = getattr(usage, 'completion_tokens', None) or 0
                self.total_input_tokens += in_tok
                self.total_output_tokens += out_tok
                output_tokens = getattr(usage, 'completion_tokens', None)
                if output_tokens and output_tokens >= max_tokens - 50:
                    print(f"   WARNING: output token limit reached "
                          f"({output_tokens}/{max_tokens}). "
                          f"Will attempt to parse partial output instead of failing the batch.")

            if not response or not getattr(response, 'choices', None):
                raise ValueError("Empty response from API")

            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("Empty content in API response")

            print(f"   DEBUG: Input note (first 300 chars): {notes[0][:300] if notes else 'N/A'}...")
            print(f"   DEBUG: Raw API response (first 500 chars): {content[:500]}...")

            if '<!doctype' in content.lower() or '<html' in content.lower() or '404' in content:
                raise ValueError(f"API returned HTML error page instead of JSON. Response starts with: {content[:200]}")

            structured_data = self._parse_json_response(content, len(notes))
            if not structured_data:
                raise ValueError("Failed to parse response into structured data")

            print(f"   DEBUG: Parsed {len(structured_data)} records")
            if structured_data:
                print(f"   DEBUG: First record keys: {list(structured_data[0].keys())}")

            structured_data = [self._normalize_record(record) for record in structured_data]
            if len(structured_data) != len(notes):
                structured_data = self._fix_count(structured_data, len(notes))

            if self._records_are_all_empty(structured_data):
                if retry_count < self.max_retries - 1:
                    raise ValueError("All extracted records are empty — retrying")
                else:
                    print("   WARNING: All records empty after all retries")

            print(f"   Successfully extracted {len(structured_data)} records "
                  f"({processing_time:.1f}s)")
            return structured_data

        except Exception as e:
            if retry_count < self.max_retries - 1:
                wait_time = 2 ** retry_count
                print(f"   Retrying in {wait_time}s... ({e})")
                time.sleep(wait_time)
                return self.extract_features(notes, diagnosis_context, retry_count + 1)

            print(f"   ERROR after {self.max_retries} retries: {e}")
            return self._get_fallback_structures(len(notes))

    # ------------------------------------------------------------------ #
    #  JSON parsing helpers (department-agnostic)                        #
    # ------------------------------------------------------------------ #

    def _strip_markdown(self, content: str) -> str:
        content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL)
        content = re.sub(r'```(?:json)?\s*', '', content)
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        import html as _html
        content = _html.unescape(content)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<[^>]+>', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        return content

    def _parse_json_response(self, content: str, expected_count: int) -> List[Dict]:
        content = content.strip()

        cleaned_first = self._strip_markdown(content)
        try:
            data = json.loads(cleaned_first)
            records = self._extract_records(data)
            if records:
                return records
        except json.JSONDecodeError as e:
            print(f"   DEBUG: Strategy 1 failed - {e}")

        results_match = re.search(r'"results"\s*:\s*(\[)', content)
        if results_match:
            arr_start = results_match.start(1)
            arr_candidate = self._extract_array_from_pos(content, arr_start)
            if arr_candidate:
                try:
                    data = json.loads(arr_candidate)
                    if isinstance(data, list):
                        return data
                except json.JSONDecodeError as e:
                    print(f"   DEBUG: Strategy 2 failed - {e}")

        array_json = self._extract_array(content)
        if array_json:
            try:
                data = json.loads(array_json)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError as e:
                print(f"   DEBUG: Strategy 3 failed - {e}")

        obj_json = self._extract_object(content)
        if obj_json:
            try:
                data = json.loads(obj_json)
                records = self._extract_records(data)
                if records:
                    return records
            except json.JSONDecodeError as e:
                print(f"   DEBUG: Strategy 4 failed - {e}")

        line_json = self._find_json_in_lines(content)
        if line_json:
            try:
                data = json.loads(line_json)
                records = self._extract_records(data)
                if records:
                    return records
            except json.JSONDecodeError as e:
                print(f"   DEBUG: Strategy 5 failed - {e}")

        print(f"   DEBUG: All parsing strategies failed. Content starts with: {content[:200]}...")
        return []

    def _extract_array_from_pos(self, content: str, start: int) -> Optional[str]:
        stack = []
        in_string = False
        escape_next = False
        for i in range(start, len(content)):
            ch = content[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '[':
                stack.append('[')
            elif ch == ']':
                if stack:
                    stack.pop()
                    if not stack:
                        return content[start:i + 1]
        return None

    def _extract_array(self, content: str) -> Optional[str]:
        first_bracket = content.find('[')
        if first_bracket == -1:
            return None
        return self._extract_array_from_pos(content, first_bracket)

    def _extract_object(self, content: str) -> Optional[str]:
        stack = []
        start_idx = -1
        in_string = False
        escape_next = False

        for i, ch in enumerate(content):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == '{':
                if not stack:
                    start_idx = i
                stack.append('{')
            elif ch == '}':
                if stack:
                    stack.pop()
                    if not stack and start_idx != -1:
                        return content[start_idx:i + 1]

        return None

    def _find_json_in_lines(self, content: str) -> Optional[str]:
        lines = content.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('[') or line.startswith('{'):
                remaining = '\n'.join(lines[i:])
                if line.startswith('['):
                    extracted = self._extract_array(remaining)
                else:
                    extracted = self._extract_object(remaining)
                if extracted:
                    return extracted
        return None

    def _extract_records(self, data) -> List[Dict]:
        if isinstance(data, list):
            if all(isinstance(item, dict) for item in data):
                return data
            return []

        if isinstance(data, dict):
            for key in ['results', 'data', 'notes', 'extracted_features', 'records']:
                if key in data and isinstance(data[key], list):
                    return data[key]

            if self._is_valid_record(data):
                return [data]

            for value in data.values():
                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    return value

            return [data]

        return []

    def _is_valid_record(self, obj: Dict) -> bool:
        if not isinstance(obj, dict):
            return False
        keys = set(obj.keys())
        required = set(self.required_fields)
        overlap = len(keys.intersection(required))
        return overlap >= len(required) * 0.3

    def _records_are_all_empty(self, records: List[Dict]) -> bool:
        for record in records:
            for field in self.required_fields:
                val = record.get(field)
                if val and str(val).strip():
                    return False
        return True

    def _normalize_record(self, record: Dict) -> Dict:
        """Normalize to only required fields, using this department's alias map.
        Falls back to a case-insensitive match for keys not covered by the
        explicit alias table, so minor casing differences from the model
        never silently drop data."""
        normalized = {field: "" for field in self.required_fields}
        canonical_lower = {f.lower(): f for f in self.required_fields}

        for key, value in record.items():
            canonical = self.field_aliases.get(key, key)
            if canonical not in self.required_fields:
                canonical = canonical_lower.get(canonical.lower(), canonical)
            if canonical in self.required_fields:
                normalized[canonical] = value if value is not None else ""

        return normalized

    def _fix_count(self, records: List[Dict], expected: int) -> List[Dict]:
        if len(records) < expected:
            while len(records) < expected:
                records.append({field: "" for field in self.required_fields})
        elif len(records) > expected:
            records = records[:expected]
        return records

    def _get_fallback_structures(self, count: int) -> List[Dict]:
        return [{field: "" for field in self.required_fields} for _ in range(count)]

    def extract_batch(
        self,
        notes: List[str],
        diagnosis_context: Optional[List[Dict]] = None,
        batch_size: int = 3,
        progress_callback=None,
        rate_limit_delay: float = 1.0
    ) -> List[Dict]:
        """Extract features in batches."""
        all_results = []
        total_batches = (len(notes) + batch_size - 1) // batch_size
        failed_batches = []

        for i in range(0, len(notes), batch_size):
            batch = notes[i:i + batch_size]
            batch_context = diagnosis_context[i:i + batch_size] if diagnosis_context else None
            batch_number = i // batch_size + 1

            if progress_callback:
                try:
                    progress_callback(batch_number, total_batches, f"Batch {batch_number}/{total_batches}")
                except Exception:
                    pass

            try:
                results = self.extract_features(batch, diagnosis_context=batch_context)

                if not results or len(results) != len(batch):
                    results = self._fix_count(results if results else [], len(batch))
                    failed_batches.append(batch_number)

                all_results.extend(results)

                if i + batch_size < len(notes):
                    time.sleep(rate_limit_delay)

            except Exception as e:
                print(f"   Batch {batch_number} failed: {e}")
                all_results.extend(self._get_fallback_structures(len(batch)))
                failed_batches.append(batch_number)

        if failed_batches:
            print(f"   Batches with issues: {failed_batches}")

        return all_results
