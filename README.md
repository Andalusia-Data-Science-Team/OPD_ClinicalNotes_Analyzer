# OPD AI Clinical Analyzer

🤖 **AI-Powered Clinical Notes Extraction System for Outpatient Department**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![SQL Server](https://img.shields.io/badge/Database-SQL%20Server-red.svg)](https://microsoft.com/sql-server)
[![AI](https://img.shields.io/badge/AI-Fireworks%20AI-purple.svg)](https://fireworks.ai)

## 🎯 Overview

The **OPD AI Clinical Analyzer** is a production-ready healthcare AI system that automatically extracts structured medical information from outpatient clinical notes using advanced natural language processing. The system processes raw clinical documentation and converts it into standardized, analyzable data ready for clinical analytics and reporting.

### 🏥 Healthcare Use Cases
- **Clinical Documentation Enhancement** - Structure unstructured notes
- **Quality Assurance** - Validate completeness of clinical documentation
- **Data Analytics** - Enable structured analysis of clinical patterns
- **Research Support** - Convert clinical notes to research-ready datasets
- **Compliance Reporting** - Standardize documentation for regulatory requirements

## ✨ Key Features

### 🚀 Core Capabilities
- **🤖 AI-Powered Extraction** - Advanced NLP with Fireworks AI models
- **📊 Structured Output** - 7 standardized medical fields extracted
- **🔄 Batch Processing** - Scalable processing of large note volumes
- **🛡️ Robust Parsing** - 6-strategy JSON parsing with fallback mechanisms
- **📈 Quality Scoring** - Automated documentation completeness assessment
- **🔒 Database Integration** - Direct SQL Server connectivity

### 🎯 Extracted Medical Fields
| Field | Description |
|-------|-------------|
| **Chief_Complain** | Primary reason for patient visit |
| **History** | Patient medical history details |
| **Allergy** | Documented allergies and reactions |
| **Comorbidities** | Co-existing medical conditions |
| **Clinical_Examination** | Physical examination findings |
| **Diagnosis** | Clinical diagnosis information |
| **Treatment_Plan** | Prescribed treatments and follow-up |

### 🛠️ Technical Features
- **Modular Architecture** - Clean separation of concerns
- **Error Handling** - Comprehensive retry logic and error recovery
- **Configuration Management** - Environment-based settings
- **Progress Tracking** - Real-time processing feedback
- **Rate Limiting** - API throttling compliance
- **Data Validation** - Multi-level quality checks

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   SQL Server    │───▶│  Pipeline Core   │───▶│   SQL Server    │
│  (Source Data)  │    │   Processing    │    │ (Results DB)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Fireworks AI   │
                       │   Extraction    │
                       └──────────────────┘
```

### 📁 Project Structure
```
OPD-Clean/
├── clinical_notes_pipeline.py          # Main orchestration script
├── .env                            # Environment configuration
├── src/
│   ├── config.py                    # Configuration management
│   ├── database_ops.py              # Database operations
│   ├── extractor.py                 # AI extraction engine
│   ├── data_processor.py            # Data validation & scoring
│   ├── utils.py                    # Utility functions
│   └── opd_prompt.py               # AI prompt engineering
├── src/OPD_query.sql               # Clinical notes query
└── requirements.txt                 # Python dependencies
```

## 🚀 Quick Start

### 📋 Prerequisites
- **Python 3.8+** - Core runtime environment
- **SQL Server** - Database for source and results
- **Fireworks AI API Key** - AI processing service
- **ODBC Driver 17** - SQL Server connectivity

### 🔧 Installation

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd OPD-Clean
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

### ⚙️ Configuration

Create `.env` file with your settings:

```bash
# Fireworks AI Configuration
FIREWORKS_API_KEY=your_api_key_here

# Database Configuration
DB_SERVER=your_server_name
DB_DATABASE=your_database_name
DB_TRUSTED_CONNECTION=no
DB_USERNAME=your_username
DB_PASSWORD=your_password

# Processing Parameters
BATCH_SIZE=3
MAX_ROWS=1000
MODEL=accounts/fireworks/models/deepseek-v3p1
TEMPERATURE=0.0

# Output Configuration
OUTPUT_SCHEMA=dbo
OUTPUT_TABLE=Clinical_Notes_Extracted
NOTES_COLUMN=Clinical_Notes
```

### 🏃‍♂️ Run Pipeline

```bash
python clinical_notes_pipeline.py
```

## 📊 Processing Workflow

### 🔄 Pipeline Steps

1. **🔧 Configuration Loading**
   - Load environment variables
   - Validate required settings
   - Initialize processing parameters

2. **🔗 Database Connection Test**
   - Verify SQL Server connectivity
   - Test authentication credentials
   - Validate query permissions

3. **📥 Data Loading**
   - Execute clinical notes query
   - Load notes into memory
   - Prepare for AI processing

4. **🤖 AI Extraction**
   - Process notes in configurable batches
   - Apply advanced NLP extraction
   - Handle API rate limiting
   - Implement retry logic for failures

5. **📊 Data Processing**
   - Validate extracted structure
   - Calculate documentation scores
   - Generate processing statistics

6. **💾 Database Storage**
   - Combine with original data
   - Insert results to target table
   - Maintain referential integrity

### 📈 Output Example

**Input Clinical Note:**
```
Patient presents with headache for 3 days, no allergies, 
hypertension as comorbidity, normal examination, 
diagnosed with tension headache, prescribed pain relievers.
```

**Structured Output:**
```json
{
  "Chief_Complain": "headache for 3 days",
  "History": "headache for 3 days",
  "Allergy": "",
  "Comorbidities": "hypertension",
  "Clinical_Examination": "normal examination",
  "Diagnosis": "tension headache",
  "Treatment_Plan": "prescribed pain relievers"
}
```

## 🔧 Advanced Configuration

### 🎛️ Batch Processing
```python
# Adjust for your environment
BATCH_SIZE=5          # Notes per API call
RATE_LIMIT_DELAY=1.0   # Seconds between batches
MAX_RETRIES=3          # Failed API call retries
```

### 🏥 Database Customization
```sql
-- Customize your query in src/OPD_query.sql
SELECT TOP 1000 
    Patient_ID,
    Clinical_Notes,
    Visit_Date
FROM Clinical_Documentation
WHERE Visit_Date >= DATEADD(day, -30, GETDATE())
```

### 🤖 AI Model Selection
```python
# Available models
MODEL="accounts/fireworks/models/deepseek-v3p1"  # Default
MODEL="accounts/fireworks/models/llama-v3p1-8b"  # Alternative
TEMPERATURE=0.0  # Deterministic output
```

## 🔍 Monitoring & Validation

### 📊 Quality Metrics
- **Extraction Success Rate** - Percentage of successfully processed notes
- **Field Completion Rate** - Data completeness per medical field
- **Documentation Score** - Quality assessment of each extraction
- **Processing Speed** - Notes processed per minute

### 🛡️ Error Handling
- **API Failures** - Automatic retry with exponential backoff
- **JSON Parsing Errors** - 6-strategy fallback parsing
- **Database Errors** - Transaction rollback and error reporting
- **Data Validation** - Schema compliance checking

## 🚀 Performance Optimization

### ⚡ Speed Optimizations
- **Batch Processing** - Process multiple notes per API call
- **Connection Pooling** - Reuse database connections
- **Memory Management** - Efficient data structure handling
- **Rate Limiting** - Comply with API constraints

### 📈 Scalability
- **Horizontal Scaling** - Multiple pipeline instances
- **Database Partitioning** - Process large datasets efficiently
- **Caching** - Reduce redundant API calls
- **Parallel Processing** - Concurrent batch execution

## 🔒 Security & Compliance

### 🛡️ Data Protection
- **Environment Variables** - No hardcoded credentials
- **SQL Injection Prevention** - Parameterized queries
- **API Key Security** - Secure credential management
- **Data Encryption** - Secure database connections

### 🏥 Healthcare Compliance
- **HIPAA Considerations** - Protected health information handling
- **Data Retention** - Configurable data lifecycle policies
- **Audit Logging** - Complete processing audit trail
- **Access Controls** - Role-based database permissions

## 🐛 Troubleshooting

### 🔧 Common Issues

**Database Connection Errors:**
```bash
# Check ODBC driver
pyodbc.drivers()

# Test connection string
python -c "import pyodbc; conn = pyodbc.connect('your_connection_string')"
```

**API Authentication:**
```bash
# Verify API key
curl -H "Authorization: Bearer $FIREWORKS_API_KEY" \
     https://api.fireworks.ai/v1/models
```

**Memory Issues:**
```python
# Reduce batch size
BATCH_SIZE=1  # For large clinical notes
```

### 📝 Debug Mode
```python
# Enable verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Contributing

### 📋 Development Setup
1. Fork the repository
2. Create feature branch
3. Add unit tests for new functionality
4. Ensure all tests pass
5. Submit pull request

### 🧪 Testing
```bash
# Run test suite
python -m pytest tests/

# Validate extraction quality
python tests/validation_test.py
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

### 🆘 Getting Help
- **Issues** - Report bugs via GitHub Issues
- **Documentation** - Check project wiki
- **Community** - Join discussions for questions

### 📧 Contact
- **Technical Support** - [support@organization.com]
- **Healthcare Queries** - [clinical@organization.com]

## 🗺️ Roadmap

### 🚀 Upcoming Features
- **📊 Dashboard Interface** - Web-based monitoring
- **🏥 Multi-Department Support** - Extend beyond OPD
- **🌐 Multi-Language Support** - International clinical notes
- **📱 Mobile Interface** - On-the-go access
- **🔍 Advanced Analytics** - Predictive insights

### 🎯 Development Goals
- **Performance Improvements** - Faster processing
- **Accuracy Enhancements** - Better extraction quality
- **Integration Options** - EHR system compatibility
- **Scalability Features** - Enterprise deployment

---

**🏥 Built for Healthcare Professionals by Healthcare Technology Experts**

*Transforming clinical documentation into actionable insights with AI*
