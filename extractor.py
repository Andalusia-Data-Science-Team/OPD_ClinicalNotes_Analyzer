import json
import re
import time 
from typing import List, Dict, Optional
from fireworks.client import Fireworks
import os 
from src.opd_prompt import SYSTEM_PROMPT, get_user_prompt

REQUIRED_FIELDS = [
    "Chief_Complain",
    "History", 
    "Allergy",
    "Comorbidities",
    "Clinical_Examination",
    "Diagnosis",
    "Treatment_Plan"
]

class ClinicalNotesExtractor:
    """
    ULTRA-STRICT JSON EXTRACTION VERSION
    Aggressively extracts JSON from any response format
    """
    
    def __init__(
        self, 
        api_key: str, 
        model: str = "accounts/fireworks/models/deepseek-v3p1", 
        temperature: float = 0.0, 
        max_retries: int = 3,
        timeout: int = 120
    ):
        if not api_key or not api_key.strip():
            raise ValueError("API key cannot be empty")
        self.cached_system_prompt = SYSTEM_PROMPT
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout

        try:
            self.client = Fireworks(api_key=api_key)
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Fireworks client: {str(e)}")       
         
    def extract_features(self, notes: List[str], diagnosis_context: Optional[List[Dict]] = None, retry_count: int = 0) -> List[Dict]:
        """Extract features with ultra-aggressive JSON parsing"""
        try:
            if not notes:
                raise ValueError("Notes list cannot be empty")
            
            user_prompt = get_user_prompt(notes, diagnosis_context=diagnosis_context)
            
            estimated_tokens = len(user_prompt) // 4
            max_tokens = min(8192, max(2000, estimated_tokens * 2))
            
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.cached_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            
            processing_time = time.time() - start_time
            
            # Capture actual token usage
            if hasattr(response, 'usage') and response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                
            else:
                print("   Token usage not available in response")
            
            if not response or not response.choices:
                raise ValueError("Empty response from API")
            
            content = response.choices[0].message.content
            
            if not content or not content.strip():
                raise ValueError("Empty content in API response")
            
            # ULTRA-AGGRESSIVE PARSING
            structured_data = self._ultra_parse(content, len(notes))
            
            if not structured_data:
                raise ValueError("Failed to parse response into structured data")
            
            # Normalize all records
            structured_data = [self._normalize_record(record) for record in structured_data]
            
            # Ensure correct count
            if len(structured_data) != len(notes):
                print(f"Count mismatch: expected {len(notes)}, got {len(structured_data)}")
                structured_data = self._fix_count(structured_data, len(notes))
            
            print(f"   Successfully extracted {len(structured_data)} records")
            return structured_data
            
        except Exception as e:
            error_msg = f"Error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}"
            print(error_msg)
            
            if retry_count < self.max_retries - 1:
                wait_time = 2 ** retry_count
                print(f"   ⏳ Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self.extract_features(notes, diagnosis_context, retry_count + 1)
            
            print(f"All {self.max_retries} retries failed")
            return self._get_empty_structures(len(notes))
    
    def _ultra_parse(self, content: str, expected_count: int) -> List[Dict]:
        content = content.strip()

        try:
            data = json.loads(content)
            records = self._extract_records(data)
            if records:
                return records
        except json.JSONDecodeError:
            print(f"   Strategy 1 failed: Not valid JSON")
        
        # STRATEGY 2: Remove markdown fences
        cleaned = self._strip_markdown(content)
        if cleaned != content:
            try:
                data = json.loads(cleaned)
                records = self._extract_records(data)
                if records:
                    print(f"   Strategy 2: Markdown removal succeeded ({len(records)} records)")
                    return records
            except json.JSONDecodeError:
                print(f"   Strategy 2 failed")
        
        # STRATEGY 3: Find JSON array pattern
        array_json = self._extract_array(content)
        if array_json:
            try:
                data = json.loads(array_json)
                if isinstance(data, list):
                    print(f"   Strategy 3: Array extraction succeeded ({len(data)} records)")
                    return data
            except json.JSONDecodeError:
                print(f"   Strategy 3 failed")
        
        # STRATEGY 4: Find JSON object pattern
        obj_json = self._extract_object(content)
        if obj_json:
            try:
                data = json.loads(obj_json)
                records = self._extract_records(data)
                if records:
                    print(f"   Strategy 4: Object extraction succeeded ({len(records)} records)")
                    return records
            except json.JSONDecodeError:
                print(f"   Strategy 4 failed")
        
        # STRATEGY 5: Aggressive bracket finding
        aggressive_json = self._aggressive_bracket_extraction(content)
        if aggressive_json:
            try:
                data = json.loads(aggressive_json)
                records = self._extract_records(data)
                if records:
                    print(f"   Strategy 5: Aggressive extraction succeeded ({len(records)} records)")
                    return records
            except json.JSONDecodeError:
                print(f"   Strategy 5 failed")
        
        # STRATEGY 6: Line-by-line search for JSON
        line_json = self._find_json_in_lines(content)
        if line_json:
            try:
                data = json.loads(line_json)
                records = self._extract_records(data)
                if records:
                    print(f"   Strategy 6: Line search succeeded ({len(records)} records)")
                    return records
            except json.JSONDecodeError:
                print(f"   Strategy 6 failed")
        
        print(f"   All 6 parsing strategies failed")
        return []
    
    def _strip_markdown(self, content: str) -> str:
        """Remove markdown code fences"""
        content = content.strip()
        
        # Remove ```json or ```
        if content.startswith('```json'):
            content = content[7:]
        elif content.startswith('```'):
            content = content[3:]
        
        if content.endswith('```'):
            content = content[:-3]
        
        return content.strip()
    
    def _extract_array(self, content: str) -> Optional[str]:
        """Extract JSON array using regex"""
        # Match [ ... ] with nested structures
        pattern = r'\[(?:[^\[\]]|\[[^\[\]]*\])*\]'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            return match.group()
        
        # Try simpler pattern
        first_bracket = content.find('[')
        last_bracket = content.rfind(']')
        
        if first_bracket != -1 and last_bracket > first_bracket:
            return content[first_bracket:last_bracket + 1]
        
        return None
    
    def _extract_object(self, content: str) -> Optional[str]:
        """Extract JSON object using regex"""
        # Find first { and last }
        first_brace = content.find('{')
        last_brace = content.rfind('}')
        
        if first_brace != -1 and last_brace > first_brace:
            potential = content[first_brace:last_brace + 1]
            
            # Quick validation - count braces
            if potential.count('{') == potential.count('}'):
                return potential
        
        return None
    
    def _aggressive_bracket_extraction(self, content: str) -> Optional[str]:
        """
        Aggressively find JSON by looking for balanced brackets/braces
        """
        # Try arrays first
        stack = []
        start_idx = -1
        
        for i, char in enumerate(content):
            if char == '[':
                if not stack:
                    start_idx = i
                stack.append('[')
            elif char == ']':
                if stack and stack[-1] == '[':
                    stack.pop()
                    if not stack and start_idx != -1:
                        # Found complete array
                        return content[start_idx:i+1]
        
        # Try objects
        stack = []
        start_idx = -1
        
        for i, char in enumerate(content):
            if char == '{':
                if not stack:
                    start_idx = i
                stack.append('{')
            elif char == '}':
                if stack and stack[-1] == '{':
                    stack.pop()
                    if not stack and start_idx != -1:
                        # Found complete object
                        return content[start_idx:i+1]
        
        return None
    
    def _find_json_in_lines(self, content: str) -> Optional[str]:
        """Search for JSON line by line"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check if this line starts with [ or {
            if line.startswith('[') or line.startswith('{'):
                # Take everything from here to end
                remaining = '\n'.join(lines[i:])
                
                # Try to extract valid JSON from it
                if line.startswith('['):
                    extracted = self._extract_array(remaining)
                else:
                    extracted = self._extract_object(remaining)
                
                if extracted:
                    return extracted
        
        return None
    
    def _extract_records(self, data) -> List[Dict]:
        """Extract list of records from parsed JSON"""
        if isinstance(data, list):
            if all(isinstance(item, dict) for item in data):
                return data
            return []
        
        if isinstance(data, dict):
            # Check common wrapper patterns
            for key in ['results', 'data', 'notes', 'extracted_features', 'records']:
                if key in data and isinstance(data[key], list):
                    return data[key]
            
            # Check if it's a valid single record
            if self._is_valid_record(data):
                return [data]
            
            # Look for any list in the dict
            for value in data.values():
                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    return value
            
            # Wrap single dict
            return [data]
        
        return []
    
    def _is_valid_record(self, obj: Dict) -> bool:
        """Check if dict looks like a clinical note record"""
        if not isinstance(obj, dict):
            return False
        
        keys = set(obj.keys())
        required = set(REQUIRED_FIELDS)
        
        # At least 30% of fields present
        overlap = len(keys.intersection(required))
        return overlap >= len(required) * 0.3
    
    def _normalize_record(self, record: Dict) -> Dict:
        """Normalize to only required fields"""
        normalized = {field: "" for field in REQUIRED_FIELDS}
        
        for key, value in record.items():
            if key in REQUIRED_FIELDS:
                normalized[key] = value if value is not None else ""
            else:
                # Merge extra fields into Plan_Text
                if value and str(value).strip():
                    if normalized["Plan_Text"]:
                        normalized["Plan_Text"] += f"; {key}: {value}"
                    else:
                        normalized["Plan_Text"] = f"{key}: {value}"
        
        return normalized
    
    def _fix_count(self, records: List[Dict], expected: int) -> List[Dict]:
        """Fix record count mismatch"""
        if len(records) < expected:
            # Pad
            while len(records) < expected:
                records.append({field: "" for field in REQUIRED_FIELDS})
        elif len(records) > expected:
            # Truncate
            records = records[:expected]
        
        return records
    
    def _get_empty_structures(self, count: int) -> List[Dict]:
        """Generate empty structures"""
        return [{field: "" for field in REQUIRED_FIELDS} for _ in range(count)]
    
    def extract_batch(
        self, 
        notes: List[str], 
        diagnosis_context: Optional[List[Dict]] = None,
        batch_size: int = 3,  # Reduced default batch size
        progress_callback=None,
        rate_limit_delay: float = 1.0  # Increased delay
    ) -> List[Dict]:
        """Extract features in batches"""
        all_results = []
        total_batches = (len(notes) + batch_size - 1) // batch_size
        failed_batches = []
        
        print(f"\nProcessing {len(notes)} notes in {total_batches} batches (size={batch_size})")
        
        for i in range(0, len(notes), batch_size):
            batch = notes[i:i + batch_size]
            batch_context = diagnosis_context[i:i + batch_size] if diagnosis_context else None
            batch_number = i // batch_size + 1
            
            print(f"\n{'='*60}")
            print(f"Batch {batch_number}/{total_batches} ({len(batch)} notes)")
            print(f"{'='*60}")
            
            if progress_callback:
                progress_callback(batch_number, total_batches, f"Batch {batch_number}/{total_batches}")
            
            try:
                results = self.extract_features(batch, diagnosis_context=batch_context)
                
                if not results or len(results) != len(batch):
                    print(f"Batch {batch_number} issue: expected {len(batch)}, got {len(results)}")
                    results = self._fix_count(results if results else [], len(batch))
                    failed_batches.append(batch_number)
                
                all_results.extend(results)
                
                # Rate limiting
                if i + batch_size < len(notes):
                    time.sleep(rate_limit_delay)
            
            except Exception as e:
                print(f"Batch {batch_number} error: {e}")
                all_results.extend(self._get_empty_structures(len(batch)))
                failed_batches.append(batch_number)
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Batch Processing Complete")
        print(f"{'='*60}")
        print(f"Total batches: {total_batches}")
        print(f"Successful: {total_batches - len(failed_batches)}")
        print(f"Failed: {len(failed_batches)}")
        if failed_batches:
            print(f"Failed batch numbers: {failed_batches}")
        
        return all_results
