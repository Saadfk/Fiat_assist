import os
import subprocess
import winreg
from datetime import datetime

# Prepare log file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = f"Windows11_Security_Audit_{timestamp}.log"
log_lines = []  # accumulate lines to write

def log(section, message):
    """Helper to format log entries."""
    log_lines.append(f"{section}: {message}")

# 1. BitLocker Status
section = "[BitLocker]"
try:
    result = subprocess.run(["manage-bde", "-status"], capture_output=True, text=True)
    bitlocker_output = result.stdout
    if "Percentage Encrypted: 100%" in bitlocker_output and "Protection Status: Protection On" in bitlocker_output:
        log(section, "Enabled (drive is fully encrypted)")
    else:
        log(section, "Not Enabled or not fully encrypted!")
except Exception as e:
    log(section, f"Error checking BitLocker status: {e}")

# 2. Windows Firewall Status
section = "[Firewall]"
try:
    result = subprocess.run(["netsh", "advfirewall", "show", "allprofiles"], capture_output=True, text=True)
    fw_output = result.stdout
    # Look for lines like "State ON" or "State OFF" under each profile
    profiles = {"Domain": None, "Private": None, "Public": None}
    for line in fw_output.splitlines():
        line = line.strip()
        for prof in profiles:
            if line.startswith(f"{prof} Profile Settings"):
                current_profile = prof
            if line.startswith("State"):
                state = line.split()[-1]
                profiles[current_profile] = state
    for prof, state in profiles.items():
        if state == "ON":
            log(section, f"{prof} firewall: Enabled")
        elif state == "OFF":
            log(section, f"{prof} firewall: **Disabled**")
        else:
            log(section, f"{prof} firewall: Unknown state")
except Exception as e:
    log(section, f"Error checking firewall: {e}")

# 3. DNS Configuration
section = "[DNS]"
try:
    result = subprocess.run(["netsh", "interface", "ipv4", "show", "dnsservers"], capture_output=True, text=True)
    dns_output = result.stdout
    # Parse DNS servers from output
    dns_servers = []
    for line in dns_output.splitlines():
        line = line.strip()
        if line.lower().startswith("dns servers") or line.lower().startswith("statistically"):
            # Skip header lines or empty
            continue
        if line:
            # Expect lines that contain the DNS IP (ignoring interface names above)
            parts = line.split(":")
            if len(parts) == 2 and parts[1].strip():
                dns_ip = parts[1].strip()
                # Validate format superficially
                if dns_ip[0].isdigit():
                    dns_servers.append(dns_ip)
    if dns_servers:
        dns_list = ", ".join(dns_servers)
        # Check against known good servers if desired (e.g., Google or Cloudflare)
        expected = {"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"}
        if all(ip in expected for ip in dns_servers):
            log(section, f"Servers = {dns_list} (OK)")
        else:
            log(section, f"Servers = {dns_list} (Check if these are approved)")
    else:
        log(section, "No DNS servers found or DHCP default (Needs review)")
except Exception as e:
    log(section, f"Error checking DNS: {e}")

# 4. Account Policies (Password Policy)
section = "[Account Policies]"
try:
    result = subprocess.run(["net", "accounts"], capture_output=True, text=True)
    acct_output = result.stdout
    # We can directly log the whole output or parse specific lines
    # Here, we'll extract a few key settings
    for line in acct_output.splitlines():
        if line.strip().startswith(("Minimum password length", "Minimum password age",
                                     "Maximum password age", "Lockout threshold",
                                     "Lockout duration", "Lockout observation window")):
            log(section, line.strip())
except Exception as e:
    log(section, f"Error retrieving account policies: {e}")

# 5. USB Boot Disabled (registry policy check if any)
section = "[USB Boot]"
try:
    # Check if a registry key for external boot exists (common in DeviceGuard/DFCI)
    reg_path = r"SYSTEM\CurrentControlSet\Control\DeviceGuard"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
        # (Example: looking for a value that might indicate external boot not allowed)
        try:
            val, _ = winreg.QueryValueEx(key, "AllowBootFromExternalMedia")
            if val == 0:
                log(section, "External boot: Disabled via policy")
            elif val == 1:
                log(section, "External boot: Allowed via policy")
            else:
                log(section, f"External boot policy value: {val}")
        except FileNotFoundError:
            log(section, "No OS policy for external boot (Check BIOS settings)")
except Exception as e:
    log(section, f"Error checking USB boot policy: {e}")

# 6. NTLM & LM Authentication
section = "[NTLM/LM]"
try:
    lsa_path = r"SYSTEM\CurrentControlSet\Control\Lsa"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, lsa_path) as lsa_key:
        # LmCompatibilityLevel
        try:
            lm_level, _ = winreg.QueryValueEx(lsa_key, "LmCompatibilityLevel")
        except FileNotFoundError:
            lm_level = None
        # NoLMHash
        try:
            nolm, _ = winreg.QueryValueEx(lsa_key, "NoLMHash")
        except FileNotFoundError:
            nolm = 0  # treat missing as 0 (not set)

    if lm_level is not None:
        # Interpret LM Compatibility level
        if lm_level >= 5:
            log(section, f"LmCompatibilityLevel = {lm_level} (NTLMv2 only, LM/NTLMv1 refused)")
        elif lm_level == 4:
            log(section, f"LmCompatibilityLevel = {lm_level} (NTLMv2 only, LM refused, NTLMv1 allowed)")
        else:
            log(section, f"LmCompatibilityLevel = {lm_level} (**Needs improvement** - legacy protocols allowed)")
    else:
        log(section, "LmCompatibilityLevel not set (using system default)")

    if nolm == 1:
        log(section, "NoLMHash = 1 (LM hashes not stored)")
    else:
        log(section, f"NoLMHash = {nolm} (**LM hashes may be stored**)")
except Exception as e:
    log(section, f"Error checking NTLM/LM settings: {e}")

# 7. Windows Recovery (WinRE) Status
section = "[WinRE]"
try:
    result = subprocess.run(["reagentc", "/info"], capture_output=True, text=True)
    re_out = result.stdout
    status_line = None
    for line in re_out.splitlines():
        if "Windows RE status" in line:
            status_line = line.strip()
            break
    if status_line:
        # e.g., "Windows RE status: Enabled"
        log(section, status_line)
        if "Disabled" in status_line:
            log(section, "WinRE is disabled (Recovery options are turned off)")
    else:
        log(section, "WinRE status: Unknown (reagentc output not as expected)")
except Exception as e:
    log(section, f"Error checking WinRE status: {e}")

# 8. Secure Boot
section = "[Secure Boot]"
try:
    sb_path = r"SYSTEM\CurrentControlSet\Control\SecureBoot\State"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sb_path) as sb_key:
        val, _ = winreg.QueryValueEx(sb_key, "UEFISecureBootEnabled")
        if val == 1:
            log(section, "Secure Boot is ENABLED")
        else:
            log(section, "Secure Boot is NOT enabled")
except FileNotFoundError:
    log(section, "Secure Boot state not found (system may not support Secure Boot)")
except Exception as e:
    log(section, f"Error checking Secure Boot: {e}")

# 9. Network Services (RDP and Remote Registry)
section = "[Network Services]"
try:
    # Remote Desktop (Terminal Services) status via fDenyTSConnections
    ts_path = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ts_path) as ts_key:
        deny_val, _ = winreg.QueryValueEx(ts_key, "fDenyTSConnections")
        if deny_val == 1:
            log(section, "Remote Desktop: Disabled (connections denied)")
        else:
            log(section, "Remote Desktop: **Enabled** (connections allowed)")
except Exception as e:
    log(section, f"Remote Desktop check failed: {e}")

try:
    # Remote Registry service startup type
    svc_path = r"SYSTEM\CurrentControlSet\Services\RemoteRegistry"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, svc_path) as rr_key:
        start_val, _ = winreg.QueryValueEx(rr_key, "Start")
        # 4 = Disabled, 3 = Manual, 2 = Auto
        if start_val == 4:
            log(section, "Remote Registry: Disabled")
        elif start_val in (2, 3):
            # Also check if service is currently running
            # We can use 'sc query' for running state if needed
            svc_check = subprocess.run(["sc", "query", "RemoteRegistry"], capture_output=True, text=True).stdout
            if "RUNNING" in svc_check:
                log(section, "Remote Registry: **Enabled and Running**")
            else:
                log(section, "Remote Registry: Enabled (service not running currently)")
        else:
            log(section, f"Remote Registry: Start={start_val} (non-standard value)")
except Exception as e:
    log(section, f"Remote Registry check failed: {e}")

# Write the collected log lines to the file
with open(log_path, "w") as f:
    f.write("Windows 11 Security Audit Report - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
    f.write("\n".join(log_lines))

print(f"Security audit completed. Report saved to {log_path}")
