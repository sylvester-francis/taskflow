#!/usr/bin/env python3
"""
Security Report Generator for TaskFlow
Aggregates results from multiple security scanning tools
"""

import json
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path
from jinja2 import Template


def load_json_file(filepath):
    """Load JSON file safely"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return {}


def load_text_file(filepath):
    """Load text file safely"""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return ""


def parse_bandit_results(results_dir):
    """Parse Bandit security scan results"""
    bandit_file = results_dir / "sast-results" / "bandit-results.json"
    bandit_data = load_json_file(bandit_file)
    
    if not bandit_data:
        return {"issues": [], "summary": {"total": 0, "high": 0, "medium": 0, "low": 0}}
    
    issues = bandit_data.get("results", [])
    summary = {
        "total": len(issues),
        "high": len([i for i in issues if i.get("issue_severity") == "HIGH"]),
        "medium": len([i for i in issues if i.get("issue_severity") == "MEDIUM"]),
        "low": len([i for i in issues if i.get("issue_severity") == "LOW"])
    }
    
    return {"issues": issues, "summary": summary}


def parse_trivy_results(results_dir):
    """Parse Trivy container security scan results"""
    trivy_file = results_dir / "container-scan-results" / "trivy-detailed.json"
    trivy_data = load_json_file(trivy_file)
    
    if not trivy_data:
        return {"vulnerabilities": [], "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}}
    
    vulnerabilities = []
    summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
    
    for result in trivy_data.get("Results", []):
        for vuln in result.get("Vulnerabilities", []):
            vulnerabilities.append(vuln)
            severity = vuln.get("Severity", "UNKNOWN").lower()
            summary["total"] += 1
            summary[severity] = summary.get(severity, 0) + 1
    
    return {"vulnerabilities": vulnerabilities, "summary": summary}


def parse_semgrep_results(results_dir):
    """Parse Semgrep SAST scan results"""
    semgrep_file = results_dir / "sast-results" / "semgrep-results.json"
    semgrep_data = load_json_file(semgrep_file)
    
    if not semgrep_data:
        return {"findings": [], "summary": {"total": 0, "error": 0, "warning": 0, "info": 0}}
    
    findings = semgrep_data.get("results", [])
    summary = {
        "total": len(findings),
        "error": len([f for f in findings if f.get("extra", {}).get("severity") == "ERROR"]),
        "warning": len([f for f in findings if f.get("extra", {}).get("severity") == "WARNING"]),
        "info": len([f for f in findings if f.get("extra", {}).get("severity") == "INFO"])
    }
    
    return {"findings": findings, "summary": summary}


def parse_safety_results(results_dir):
    """Parse Safety dependency scan results"""
    safety_file = results_dir / "sast-results" / "safety-results.json"
    safety_data = load_json_file(safety_file)
    
    if not isinstance(safety_data, list):
        return {"vulnerabilities": [], "summary": {"total": 0}}
    
    summary = {"total": len(safety_data)}
    
    return {"vulnerabilities": safety_data, "summary": summary}


def parse_zap_results(results_dir):
    """Parse OWASP ZAP DAST scan results"""
    zap_file = results_dir / "zap-results" / "report_json.json"
    zap_data = load_json_file(zap_file)
    
    if not zap_data:
        return {"alerts": [], "summary": {"total": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}}
    
    alerts = []
    summary = {"total": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}
    
    for site in zap_data.get("site", []):
        for alert in site.get("alerts", []):
            alerts.append(alert)
            risk = alert.get("riskdesc", "").lower()
            summary["total"] += 1
            
            if "high" in risk:
                summary["high"] += 1
            elif "medium" in risk:
                summary["medium"] += 1
            elif "low" in risk:
                summary["low"] += 1
            else:
                summary["informational"] += 1
    
    return {"alerts": alerts, "summary": summary}


def calculate_security_score(results):
    """Calculate overall security score based on findings"""
    base_score = 100
    
    # Deduct points for each type of finding
    deductions = 0
    
    # SAST findings
    bandit = results.get("bandit", {}).get("summary", {})
    deductions += bandit.get("high", 0) * 10
    deductions += bandit.get("medium", 0) * 5
    deductions += bandit.get("low", 0) * 1
    
    # Container vulnerabilities
    trivy = results.get("trivy", {}).get("summary", {})
    deductions += trivy.get("critical", 0) * 15
    deductions += trivy.get("high", 0) * 8
    deductions += trivy.get("medium", 0) * 3
    deductions += trivy.get("low", 0) * 1
    
    # DAST findings
    zap = results.get("zap", {}).get("summary", {})
    deductions += zap.get("high", 0) * 12
    deductions += zap.get("medium", 0) * 6
    deductions += zap.get("low", 0) * 2
    
    # Dependency vulnerabilities
    safety = results.get("safety", {}).get("summary", {})
    deductions += safety.get("total", 0) * 7
    
    # Code quality issues
    semgrep = results.get("semgrep", {}).get("summary", {})
    deductions += semgrep.get("error", 0) * 8
    deductions += semgrep.get("warning", 0) * 3
    
    final_score = max(0, base_score - deductions)
    
    # Determine grade
    if final_score >= 95:
        grade = "A+"
    elif final_score >= 90:
        grade = "A"
    elif final_score >= 85:
        grade = "A-"
    elif final_score >= 80:
        grade = "B+"
    elif final_score >= 75:
        grade = "B"
    elif final_score >= 70:
        grade = "B-"
    elif final_score >= 65:
        grade = "C+"
    elif final_score >= 60:
        grade = "C"
    elif final_score >= 55:
        grade = "C-"
    elif final_score >= 50:
        grade = "D"
    else:
        grade = "F"
    
    return {"score": final_score, "grade": grade, "deductions": deductions}


def generate_html_report(results, output_file):
    """Generate HTML security report"""
    template_content = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TaskFlow Security Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { text-align: center; border-bottom: 2px solid #e0e0e0; padding-bottom: 20px; margin-bottom: 30px; }
        .score-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 30px; }
        .score-number { font-size: 3em; font-weight: bold; margin: 10px 0; }
        .grade { font-size: 1.5em; opacity: 0.9; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .summary-card { border: 1px solid #ddd; border-radius: 8px; padding: 15px; background: #fafafa; }
        .summary-card h3 { margin-top: 0; color: #333; }
        .metric { display: flex; justify-content: space-between; margin: 8px 0; }
        .critical { color: #dc3545; font-weight: bold; }
        .high { color: #fd7e14; font-weight: bold; }
        .medium { color: #ffc107; font-weight: bold; }
        .low { color: #28a745; }
        .details { margin-top: 30px; }
        .tool-section { margin-bottom: 25px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }
        .tool-section h3 { color: #495057; border-bottom: 1px solid #dee2e6; padding-bottom: 10px; }
        .timestamp { color: #6c757d; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔒 TaskFlow Security Report</h1>
            <p class="timestamp">Generated on {{ timestamp }}</p>
        </div>
        
        <div class="score-card">
            <div class="score-number">{{ security_score.score }}/100</div>
            <div class="grade">Security Grade: {{ security_score.grade }}</div>
        </div>
        
        <div class="summary-grid">
            {% if bandit.summary.total > 0 %}
            <div class="summary-card">
                <h3>🔍 SAST Scan (Bandit)</h3>
                <div class="metric">Total Issues: <span>{{ bandit.summary.total }}</span></div>
                <div class="metric">High: <span class="high">{{ bandit.summary.high }}</span></div>
                <div class="metric">Medium: <span class="medium">{{ bandit.summary.medium }}</span></div>
                <div class="metric">Low: <span class="low">{{ bandit.summary.low }}</span></div>
            </div>
            {% endif %}
            
            {% if trivy.summary.total > 0 %}
            <div class="summary-card">
                <h3>🐳 Container Scan (Trivy)</h3>
                <div class="metric">Total Vulnerabilities: <span>{{ trivy.summary.total }}</span></div>
                <div class="metric">Critical: <span class="critical">{{ trivy.summary.critical }}</span></div>
                <div class="metric">High: <span class="high">{{ trivy.summary.high }}</span></div>
                <div class="metric">Medium: <span class="medium">{{ trivy.summary.medium }}</span></div>
                <div class="metric">Low: <span class="low">{{ trivy.summary.low }}</span></div>
            </div>
            {% endif %}
            
            {% if semgrep.summary.total > 0 %}
            <div class="summary-card">
                <h3>⚡ Code Quality (Semgrep)</h3>
                <div class="metric">Total Findings: <span>{{ semgrep.summary.total }}</span></div>
                <div class="metric">Errors: <span class="high">{{ semgrep.summary.error }}</span></div>
                <div class="metric">Warnings: <span class="medium">{{ semgrep.summary.warning }}</span></div>
                <div class="metric">Info: <span class="low">{{ semgrep.summary.info }}</span></div>
            </div>
            {% endif %}
            
            {% if safety.summary.total > 0 %}
            <div class="summary-card">
                <h3>📦 Dependencies (Safety)</h3>
                <div class="metric">Vulnerable Packages: <span class="high">{{ safety.summary.total }}</span></div>
            </div>
            {% endif %}
            
            {% if zap.summary.total > 0 %}
            <div class="summary-card">
                <h3>🌐 DAST Scan (ZAP)</h3>
                <div class="metric">Total Alerts: <span>{{ zap.summary.total }}</span></div>
                <div class="metric">High Risk: <span class="high">{{ zap.summary.high }}</span></div>
                <div class="metric">Medium Risk: <span class="medium">{{ zap.summary.medium }}</span></div>
                <div class="metric">Low Risk: <span class="low">{{ zap.summary.low }}</span></div>
            </div>
            {% endif %}
        </div>
        
        <div class="details">
            <h2>📋 Recommendations</h2>
            <ul>
                {% if trivy.summary.critical > 0 %}
                <li><strong>Critical:</strong> Address {{ trivy.summary.critical }} critical container vulnerabilities immediately</li>
                {% endif %}
                {% if bandit.summary.high > 0 %}
                <li><strong>High Priority:</strong> Fix {{ bandit.summary.high }} high-severity code security issues</li>
                {% endif %}
                {% if safety.summary.total > 0 %}
                <li><strong>Dependencies:</strong> Update {{ safety.summary.total }} vulnerable dependencies</li>
                {% endif %}
                {% if zap.summary.high > 0 %}
                <li><strong>Web Security:</strong> Address {{ zap.summary.high }} high-risk web vulnerabilities</li>
                {% endif %}
                {% if security_score.score >= 90 %}
                <li><strong>Excellent:</strong> Maintain current security practices</li>
                {% elif security_score.score >= 80 %}
                <li><strong>Good:</strong> Address medium and high priority issues to improve score</li>
                {% elif security_score.score >= 60 %}
                <li><strong>Needs Improvement:</strong> Focus on critical and high severity vulnerabilities</li>
                {% else %}
                <li><strong>Action Required:</strong> Immediate security improvements needed</li>
                {% endif %}
            </ul>
        </div>
        
        <div class="details">
            <h2>🔧 Next Steps</h2>
            <ol>
                <li>Review and fix critical and high severity vulnerabilities</li>
                <li>Update vulnerable dependencies to patched versions</li>
                <li>Implement additional security headers and configurations</li>
                <li>Regular security scanning in CI/CD pipeline</li>
                <li>Security awareness training for development team</li>
            </ol>
        </div>
    </div>
</body>
</html>
    '''
    
    template = Template(template_content)
    html_content = template.render(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        **results
    )
    
    with open(output_file, 'w') as f:
        f.write(html_content)


def generate_markdown_summary(results, output_file):
    """Generate markdown summary for PR comments"""
    summary_content = f"""
## 🔒 Security Scan Summary

**Security Score: {results['security_score']['score']}/100 (Grade: {results['security_score']['grade']})**

### 📊 Scan Results

| Tool | Critical | High | Medium | Low | Total |
|------|----------|------|--------|-----|-------|
| Trivy (Container) | {results['trivy']['summary'].get('critical', 0)} | {results['trivy']['summary'].get('high', 0)} | {results['trivy']['summary'].get('medium', 0)} | {results['trivy']['summary'].get('low', 0)} | {results['trivy']['summary'].get('total', 0)} |
| Bandit (SAST) | - | {results['bandit']['summary'].get('high', 0)} | {results['bandit']['summary'].get('medium', 0)} | {results['bandit']['summary'].get('low', 0)} | {results['bandit']['summary'].get('total', 0)} |
| Safety (Deps) | - | {results['safety']['summary'].get('total', 0)} | - | - | {results['safety']['summary'].get('total', 0)} |
| ZAP (DAST) | - | {results['zap']['summary'].get('high', 0)} | {results['zap']['summary'].get('medium', 0)} | {results['zap']['summary'].get('low', 0)} | {results['zap']['summary'].get('total', 0)} |

### 🎯 Priority Actions

"""
    
    # Add priority recommendations
    critical_issues = results['trivy']['summary'].get('critical', 0)
    high_bandit = results['bandit']['summary'].get('high', 0)
    high_zap = results['zap']['summary'].get('high', 0)
    vulnerable_deps = results['safety']['summary'].get('total', 0)
    
    if critical_issues > 0:
        summary_content += f"- ⚠️ **{critical_issues} critical container vulnerabilities** - Address immediately\n"
    
    if high_bandit > 0:
        summary_content += f"- 🔴 **{high_bandit} high-severity code issues** - Review and fix\n"
    
    if vulnerable_deps > 0:
        summary_content += f"- 📦 **{vulnerable_deps} vulnerable dependencies** - Update packages\n"
    
    if high_zap > 0:
        summary_content += f"- 🌐 **{high_zap} high-risk web vulnerabilities** - Security configuration needed\n"
    
    if critical_issues == 0 and high_bandit == 0 and high_zap == 0 and vulnerable_deps == 0:
        summary_content += "- ✅ **No critical issues found** - Good security posture\n"
    
    summary_content += f"\n**Full report available in build artifacts**\n"
    
    with open(output_file, 'w') as f:
        f.write(summary_content)


def main():
    if len(sys.argv) != 2:
        print("Usage: generate-security-report.py <results_directory>")
        sys.exit(1)
    
    results_dir = Path(sys.argv[1])
    
    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} does not exist")
        sys.exit(1)
    
    print("Generating TaskFlow security report...")
    
    # Parse results from all security tools
    results = {
        "bandit": parse_bandit_results(results_dir),
        "trivy": parse_trivy_results(results_dir),
        "semgrep": parse_semgrep_results(results_dir),
        "safety": parse_safety_results(results_dir),
        "zap": parse_zap_results(results_dir),
    }
    
    # Calculate security score
    results["security_score"] = calculate_security_score(results)
    
    # Generate reports
    generate_html_report(results, "security-report.html")
    generate_markdown_summary(results, "security-summary.md")
    
    # Save JSON report
    with open("security-report.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print("✅ Security report generated successfully!")
    print(f"   Security Score: {results['security_score']['score']}/100 (Grade: {results['security_score']['grade']})")
    print("   Reports created:")
    print("   - security-report.html (detailed report)")
    print("   - security-report.json (machine readable)")
    print("   - security-summary.md (PR summary)")


if __name__ == "__main__":
    main()