from flask import Flask, request, jsonify
from flask_cors import CORS
import vertexai
from vertexai.generative_models import GenerativeModel, Part, Tool
from vertexai.preview.generative_models import grounding
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Initialize Vertex AI
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "molten-album-478703-d8")
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

vertexai.init(project=PROJECT_ID, location=LOCATION)

# Initialize Claude on Vertex AI
# Claude 3.5 Sonnet is available on Vertex AI as "claude-3-5-sonnet@20240620"
model = GenerativeModel("claude-3-5-sonnet@20240620")

# Database schema for employee data
EMPLOYEE_SCHEMA = {
    "fields": {
        "demographics": ["first_name", "last_name", "gender", "country_of_birth", "birth_year"],
        "location": ["location_city"],
        "job_info": ["job_profile", "job_title", "job_family_group", "job_family_name", "job_code"],
        "organization": ["supervisory_organization_siglum", "band"],
        "classification": ["blue_white_collar", "worker_type", "worker_status"],
        "time_tracking": ["planned_hours", "overtime_hours"],
        "employment_dates": ["start_date", "termination_date"]
    },
    "common_analyses": {
        "attrition": {
            "key_fields": ["termination_date", "worker_status", "start_date", "job_family_name", "band", "location_city"],
            "metrics": ["attrition_rate", "average_tenure", "terminations_by_period", "retention_rate"],
            "recommended_charts": ["line_chart_trend", "bar_chart_by_department", "donut_chart_by_reason"]
        },
        "hours": {
            "key_fields": ["planned_hours", "overtime_hours", "job_title", "blue_white_collar", "location_city", "worker_type"],
            "metrics": ["total_hours", "overtime_percentage", "average_hours_per_employee"],
            "recommended_charts": ["bar_chart_by_location", "pie_chart_collar_type", "line_chart_overtime_trend"]
        },
        "demographics": {
            "key_fields": ["gender", "country_of_birth", "birth_year", "job_family_group", "location_city"],
            "metrics": ["headcount", "diversity_metrics", "age_distribution"],
            "recommended_charts": ["pie_chart_gender", "bar_chart_age_groups", "donut_chart_location"]
        },
        "workforce_composition": {
            "key_fields": ["worker_type", "worker_status", "blue_white_collar", "band", "job_family_name"],
            "metrics": ["active_headcount", "temp_ratio", "bc_wc_ratio"],
            "recommended_charts": ["donut_chart_worker_type", "bar_chart_by_band", "pie_chart_collar"]
        }
    }
}

# Enhanced system prompt for intelligent dashboard generation
SYSTEM_PROMPT = """You are an expert AI dashboard analyst specializing in HR and workforce analytics.

Your role is to intelligently analyze user requests and generate insightful dashboards by:

1. **Understanding Intent**: Deeply analyze what the user wants to know
2. **Smart Field Selection**: Choose the most relevant fields from the employee database
3. **Contextual Insights**: Don't just show data - provide analytical insights
4. **Appropriate Visualizations**: Select chart types that best tell the story
5. **Proactive Recommendations**: Suggest additional analyses they might not have considered

AVAILABLE DATA SCHEMA:
{schema}

ANALYSIS FRAMEWORK:
For each request, consider:
- Primary objective: What question is the user trying to answer?
- Key dimensions: Which fields provide the most insight?
- Temporal aspects: Should we show trends over time?
- Comparative elements: What comparisons would be valuable?
- Hidden patterns: What correlations might exist?

INTELLIGENCE EXAMPLES:

User asks: "attrition dashboard"
Smart response includes:
- Not just terminations, but RETENTION rate (inverse metric)
- Tenure analysis (time between start_date and termination_date)
- Risk segments (recent hires with <1 year tenure)
- Location/department hotspots
- Trend analysis (is it getting better/worse?)

User asks: "hours in Mobile, AL"
Smart response includes:
- Not just total hours, but overtime ratio
- Comparison: blue collar vs white collar overtime patterns
- Job title breakdown (which roles work most overtime?)
- Cost implications (if overtime > regular hours)
- Worker type comparison (regular vs temporary)

User asks: "workforce dashboard"
Smart response includes:
- Current headcount by multiple dimensions
- Contractor ratio and trend
- Band distribution (organizational structure health)
- Geographic distribution
- BC/WC balance by location

RESPONSE FORMAT (JSON):
{{
  "message": "Natural language explanation of what you're showing and WHY",
  "analysis_type": "attrition|hours|demographics|workforce|custom",
  "dashboard": {{
    "title": "Descriptive, action-oriented title",
    "subtitle": "Date range or context",
    "key_insights": [
      "Most important finding #1",
      "Most important finding #2",
      "Most important finding #3"
    ],
    "fields_used": ["field1", "field2", ...],
    "metrics": [
      {{
        "label": "Metric Name",
        "value": "placeholder_value",
        "calculation": "how it's calculated",
        "field": "source_field",
        "insight": "what this number means"
      }}
    ],
    "visualizations": [
      {{
        "type": "bar|line|pie|donut",
        "title": "Chart Title",
        "x_axis": "field_name",
        "y_axis": "field_name or calculation",
        "description": "What insight this chart reveals",
        "fields": ["field1", "field2"]
      }}
    ],
    "recommendations": [
      "Suggested follow-up analysis #1",
      "Suggested follow-up analysis #2"
    ]
  }}
}}

MODIFICATION HANDLING:
When user asks to modify (e.g., "change pie to bar", "add location breakdown"):
- Preserve other elements of the dashboard
- Only modify what was requested
- Explain why the new visualization might be better/different

IMPORTANT: Be proactive and intelligent. Don't just show what's asked - show what's NEEDED for true insight.
""".format(schema=json.dumps(EMPLOYEE_SCHEMA, indent=2))


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "project_id": PROJECT_ID,
        "location": LOCATION,
        "model": "claude-3-5-sonnet (Vertex AI)"
    }), 200


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        conversation_history = data.get('history', [])
        
        # Build conversation context for Vertex AI
        full_context = f"{SYSTEM_PROMPT}\n\n"
        
        # Add conversation history
        for msg in conversation_history:
            role = "User" if msg['role'] == 'user' else "Assistant"
            full_context += f"{role}: {msg['content']}\n\n"
        
        # Add current message
        full_context += f"User: {user_message}\n\nAssistant (respond in JSON format):"
        
        # Call Vertex AI
        response = model.generate_content(
            full_context,
            generation_config={
                "max_output_tokens": 2048,
                "temperature": 0.7,
                "top_p": 0.95,
            }
        )
        
        # Parse response
        assistant_message = response.text
        
        # Try to parse JSON from response
        try:
            # Sometimes Claude wraps JSON in markdown code blocks
            if "```json" in assistant_message:
                json_start = assistant_message.find("```json") + 7
                json_end = assistant_message.find("```", json_start)
                assistant_message = assistant_message[json_start:json_end].strip()
            elif "```" in assistant_message:
                json_start = assistant_message.find("```") + 3
                json_end = assistant_message.find("```", json_start)
                assistant_message = assistant_message[json_start:json_end].strip()
            
            dashboard_data = json.loads(assistant_message)
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Raw response: {assistant_message}")
            # If not valid JSON, create a simple response
            dashboard_data = {
                "message": assistant_message,
                "dashboard": None
            }
        
        return jsonify({
            "response": dashboard_data.get("message", assistant_message),
            "dashboard": dashboard_data.get("dashboard"),
            "analysis_type": dashboard_data.get("analysis_type"),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/search-trends', methods=['POST'])
def search_trends():
    """Search for industry trends and benchmarks using Vertex AI with grounding"""
    try:
        data = request.json
        topic = data.get('topic', '')
        industry = data.get('industry', 'general')
        
        # Use Vertex AI with Google Search grounding
        search_model = GenerativeModel(
            "claude-3-5-sonnet@20240620",
            tools=[Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())]
        )
        
        prompt = f"""Search for current industry benchmarks and trends for {topic} in the {industry} industry.
        
Focus on:
- Industry average metrics (e.g., attrition rates, average hours)
- Recent trends (last 12-24 months)
- Best practices
- Comparative data from reputable sources

Provide specific numbers and cite sources where possible."""

        response = search_model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 1500,
                "temperature": 0.5,
            }
        )
        
        return jsonify({
            "trends": response.text,
            "topic": topic,
            "industry": industry,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error in search-trends endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/generate-chart-data', methods=['POST'])
def generate_chart_data():
    """Generate mock data for chart visualization based on dashboard config"""
    try:
        data = request.json
        chart_config = data.get('chart_config', {})
        
        # This would normally query your actual database
        # For prototype, return intelligent mock data based on chart type
        
        chart_type = chart_config.get('type', 'bar')
        fields = chart_config.get('fields', [])
        
        # Generate contextual mock data
        if 'attrition' in str(fields).lower() or 'termination' in str(fields).lower():
            if chart_type == 'line':
                mock_data = {
                    "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                    "datasets": [{
                        "label": "Monthly Attrition Rate (%)",
                        "data": [11.2, 10.8, 12.5, 11.9, 13.2, 12.1, 11.5, 10.9, 11.8, 12.3, 11.7, 10.5]
                    }]
                }
            elif chart_type in ['pie', 'donut']:
                mock_data = {
                    "labels": ["Engineering", "Sales", "Operations", "Support", "Admin"],
                    "datasets": [{
                        "data": [28, 22, 18, 20, 12]
                    }]
                }
            else:  # bar
                mock_data = {
                    "labels": ["Band I", "Band II", "Band III", "Band IV", "Band V"],
                    "datasets": [{
                        "label": "Attrition Count",
                        "data": [15, 22, 18, 12, 8]
                    }]
                }
        
        elif 'hours' in str(fields).lower() or 'overtime' in str(fields).lower():
            if chart_type == 'line':
                mock_data = {
                    "labels": ["Week 1", "Week 2", "Week 3", "Week 4"],
                    "datasets": [
                        {
                            "label": "Planned Hours",
                            "data": [1680, 1720, 1690, 1700]
                        },
                        {
                            "label": "Overtime Hours",
                            "data": [145, 168, 152, 138]
                        }
                    ]
                }
            elif chart_type in ['pie', 'donut']:
                mock_data = {
                    "labels": ["Blue Collar", "White Collar"],
                    "datasets": [{
                        "data": [62, 38]
                    }]
                }
            else:  # bar
                mock_data = {
                    "labels": ["Mobile, AL", "Herndon, VA", "Austin, TX", "Seattle, WA"],
                    "datasets": [{
                        "label": "Avg Overtime Hours/Employee",
                        "data": [8.5, 5.2, 6.8, 4.9]
                    }]
                }
        
        else:  # Generic data
            if chart_type in ['pie', 'donut']:
                mock_data = {
                    "labels": ["Category A", "Category B", "Category C", "Category D"],
                    "datasets": [{
                        "data": [35, 28, 22, 15]
                    }]
                }
            else:
                mock_data = {
                    "labels": ["Q1", "Q2", "Q3", "Q4"],
                    "datasets": [{
                        "label": chart_config.get('title', 'Metric'),
                        "data": [65, 72, 68, 81]
                    }]
                }
        
        return jsonify(mock_data)
        
    except Exception as e:
        print(f"Error in generate-chart-data endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)