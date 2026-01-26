import shutil
import os
from typing import Dict, List, Any

def discover_arsenal() -> str:
    """
    Scans the system to discover available CLI tools and wordlists.
    Returns a formatted string summary for the agent's system prompt.
    """
    # 1. Essential Security Binaries
    tools = [
        # Network & Scanning
        "nmap", "nuclei", "sqlmap", "ffuf", "subfinder", "naabu", 
        "whatweb", "theHarvester", "feroxbuster", "kr", "tcpdump",
        
        # Identity & Credential Cracking
        "hydra", "medusa", "john", "hashcat", "mimikatz", "responder", "netexec",
        
        # Exploitation & Post-Exploitation
        "msfconsole", "searchsploit", "powershell-empire", "powersploit", "commix",
        
        # Reverse Engineering & Forensics
        "ghidra", "r2", "gdb", "bulk-extractor", "stegosuite", "steghide",
        
        # Analysis & OSINT
        "sherlock", "retire", "semgrep", "bandit", "trufflehog", "gitleaks",
        
        # System & Utilities
        "trivy", "zap-cli", "wapiti", "nikto", "gh", "git", "7z", "jq",
        "python3", "node", "go", "rustc"
    ]
    
    available_tools = []
    for tool in tools:
        if shutil.which(tool):
            available_tools.append(tool)
            
    # 2. Wordlists
    wordlist_dir = "/home/pentester/wordlists"
    available_wordlists = []
    if os.path.exists(wordlist_dir):
        available_wordlists = os.listdir(wordlist_dir)
        
    # 3. Special Features
    features = [
        "Semantic Knowledge Graph (strix.tools.knowledge_graph)",
        "StrixDB Relational Storage (strix.tools.strixdb)",
        "Advanced WAF Evasion Engine (strix.tools.security.waf_evasion)",
        "Keyless Web Search (DuckDuckGo & Browser-based)",
        "Dynamic Pacing & Timeframe Awareness"
    ]
    
    # Format the report
    report = "### 🦉 STRIXER ARSENAL DISCOVERY ###\n"
    report += f"Environment: Kali Linux (Docker Sandbox)\n\n"
    
    report += "Available CLI Tools (use via terminal_execute):\n"
    report += f"- {', '.join(available_tools)}\n\n"
    
    if available_wordlists:
        report += f"Available Wordlists (in {wordlist_dir}):\n"
        for wl in available_wordlists:
            report += f"- {wl}\n"
        report += "\n"
        
    report += "Integrated Strix Intelligence Features:\n"
    for feat in features:
        report += f"- {feat}\n"
        
    report += "\nPRO-TIP: Use 'terminal_execute' for deep CLI flags. All findings are automatically linked in the Knowledge Graph if you use 'auto_link_findings'."
    
    return report
