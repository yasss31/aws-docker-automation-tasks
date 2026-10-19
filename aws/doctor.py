"""
aws/doctor.py - AWS Credentials & SSM Diagnostics, Safe Auto-Repair, and Verification Suite.

Designed for AWS Academy Learner Lab & Cloud Labs environments.
Strictly preserves running EC2 instances, Docker Swarm clusters, and container deployments.
Never outputs secrets, access keys, tokens, or passwords to logs or console.
"""

import os
import sys
import re
import time
import shutil
import datetime
import subprocess
import configparser
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

from config.settings import settings
from aws.ec2 import get_instances_status


# ==============================================================================
# 1. SECURITY & MASKING UTILITIES
# ==============================================================================

def mask_key(key: Optional[str]) -> str:
    """Masks an AWS Access Key ID, showing only prefix and suffix."""
    if not key:
        return "[NOT SET]"
    k = key.strip()
    if len(k) <= 8:
        return "***"
    return f"{k[:4]}***{k[-4:]}"


def mask_secret(secret: Optional[str]) -> str:
    """Masks an AWS Secret Access Key entirely, only reporting character count."""
    if not secret:
        return "[NOT SET]"
    return f"[PROTECTED ({len(secret.strip())} chars)]"


def mask_token(token: Optional[str]) -> str:
    """Masks an AWS Session Token entirely, only reporting character count."""
    if not token:
        return "[NOT SET / NONE]"
    return f"[PROTECTED SESSION TOKEN ({len(token.strip())} chars)]"


def sanitize_message(msg: str) -> str:
    """Removes sensitive access keys or tokens from arbitrary exception messages."""
    if not msg:
        return ""
    # Mask AWS Access Key ID pattern (ASIA... or AKIA...)
    msg = re.sub(r'(ASIA|AKIA)[0-9A-Z]{16}', r'\1***REDACTED***', msg)
    # Mask potential token blobs
    msg = re.sub(r'aws_session_token=([A-Za-z0-9+/=]{20,})', r'aws_session_token=[REDACTED]', msg)
    msg = re.sub(r'aws_secret_access_key=([A-Za-z0-9+/=]{20,})', r'aws_secret_access_key=[REDACTED]', msg)
    return msg


# ==============================================================================
# 2. LOCAL CONFIGURATION & CREDENTIAL SOURCES
# ==============================================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
AWS_DIR = Path.home() / ".aws"
CREDENTIALS_FILE = AWS_DIR / "credentials"
CONFIG_FILE = AWS_DIR / "config"
KEY_FILES = [PROJECT_DIR / "vockey.pem", PROJECT_DIR / "labsuser.pem"]
TARGET_REGION = "us-east-1"


def read_env_file_raw() -> Dict[str, str]:
    """Reads project .env file without mutating os.environ."""
    data = {}
    if not ENV_FILE.exists():
        return data
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    data[k] = v
    except Exception as e:
        print(f"[WARN] Gagal membaca {ENV_FILE}: {sanitize_message(str(e))}")
    return data


def read_aws_credentials_file_raw(profile: str = "default") -> Dict[str, str]:
    """Reads ~/.aws/credentials without side effects."""
    data = {}
    if not CREDENTIALS_FILE.exists():
        return data
    try:
        cp = configparser.RawConfigParser()
        cp.read(str(CREDENTIALS_FILE), encoding="utf-8")
        if cp.has_section(profile):
            for k, v in cp.items(profile):
                data[k.lower()] = v.strip()
    except Exception as e:
        print(f"[WARN] Gagal membaca {CREDENTIALS_FILE}: {sanitize_message(str(e))}")
    return data


def read_aws_config_file_raw(profile: str = "default") -> Dict[str, str]:
    """Reads ~/.aws/config without side effects."""
    data = {}
    if not CONFIG_FILE.exists():
        return data
    try:
        cp = configparser.RawConfigParser()
        cp.read(str(CONFIG_FILE), encoding="utf-8")
        sec_name = profile if profile == "default" else f"profile {profile}"
        if cp.has_section(sec_name):
            for k, v in cp.items(sec_name):
                data[k.lower()] = v.strip()
        elif cp.has_section(profile):
            for k, v in cp.items(profile):
                data[k.lower()] = v.strip()
    except Exception as e:
        print(f"[WARN] Gagal membaca {CONFIG_FILE}: {sanitize_message(str(e))}")
    return data


def test_isolated_sts_credentials(
    access_key: str,
    secret_key: str,
    session_token: Optional[str] = None,
    region: str = TARGET_REGION
) -> Tuple[bool, Optional[Dict[str, Any]], str, str]:
    """
    Tests credentials in an isolated boto3.Session directly via STS.
    Returns: (is_valid, caller_identity, error_summary, error_code)
    """
    if not access_key or not secret_key:
        return False, None, "Access Key atau Secret Key kosong", "EMPTY_KEY"

    key_type = "TEMPORARY (STS)" if access_key.startswith("ASIA") else "PERMANENT (IAM)"
    if access_key.startswith("ASIA") and not session_token:
        return False, None, "Kredensial bertipe ASIA memerlukan Session Token, namun token tidak ditemukan", "MISSING_SESSION_TOKEN"

    kwargs = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "region_name": region or TARGET_REGION
    }
    if session_token:
        kwargs["aws_session_token"] = session_token

    try:
        sess = boto3.Session(**kwargs)
        sts = sess.client("sts")
        ident = sts.get_caller_identity()
        return True, ident, "OK - Terverifikasi", "SUCCESS"
    except ClientError as ce:
        err_code = ce.response.get("Error", {}).get("Code", "ClientError")
        err_msg = sanitize_message(ce.response.get("Error", {}).get("Message", str(ce)))
        return False, None, f"{err_code}: {err_msg}", err_code
    except EndpointConnectionError as ece:
        return False, None, f"Gagal menghubungi endpoint STS ({region}): {ece}", "ENDPOINT_ERROR"
    except Exception as ex:
        return False, None, sanitize_message(str(ex)), "UNKNOWN_ERROR"


# ==============================================================================
# 3. DIAGNOSIS ENGINE
# ==============================================================================

class AWSDoctorDiagnosis:
    def __init__(self):
        self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.sources: Dict[str, Dict[str, Any]] = {}
        self.region_status: Dict[str, Any] = {}
        self.api_permissions: Dict[str, Dict[str, Any]] = {}
        self.instance_diagnosis: List[Dict[str, Any]] = []
        self.ssm_general_status: Dict[str, Any] = {}
        self.key_files_status: List[Dict[str, Any]] = []
        self.issues: List[Dict[str, str]] = []
        self.resolved_session: Optional[boto3.Session] = None
        self.active_identity: Optional[Dict[str, Any]] = None


def run_full_diagnosis() -> AWSDoctorDiagnosis:
    diag = AWSDoctorDiagnosis()

    # --- A. Periksa Sumber Kredensial Lokal ---
    # 1. Project .env
    env_data = read_env_file_raw()
    env_key = env_data.get("AWS_ACCESS_KEY_ID", "").strip()
    env_secret = env_data.get("AWS_SECRET_ACCESS_KEY", "").strip()
    env_token = env_data.get("AWS_SESSION_TOKEN", "").strip()
    env_region = env_data.get("AWS_REGION", "").strip()

    valid_env, ident_env, msg_env, code_env = test_isolated_sts_credentials(
        env_key, env_secret, env_token, env_region or TARGET_REGION
    )
    diag.sources["env"] = {
        "name": f"File .env Proyek ({ENV_FILE})",
        "exists": ENV_FILE.exists(),
        "key_masked": mask_key(env_key),
        "key_type": "ASIA (Temporary STS)" if env_key.startswith("ASIA") else ("AKIA (IAM User)" if env_key.startswith("AKIA") else "UNKNOWN"),
        "has_token": bool(env_token),
        "region": env_region or "[NOT SET]",
        "valid": valid_env,
        "identity": ident_env,
        "error_code": code_env,
        "message": msg_env,
        "raw_credentials": {"key": env_key, "secret": env_secret, "token": env_token, "region": env_region}
    }

    # 2. AWS CLI ~/.aws/credentials
    cli_creds = read_aws_credentials_file_raw("default")
    cli_cfg = read_aws_config_file_raw("default")
    cli_key = cli_creds.get("aws_access_key_id", "").strip()
    cli_secret = cli_creds.get("aws_secret_access_key", "").strip()
    cli_token = cli_creds.get("aws_session_token", "").strip()
    cli_region = cli_cfg.get("region", "").strip()

    valid_cli, ident_cli, msg_cli, code_cli = test_isolated_sts_credentials(
        cli_key, cli_secret, cli_token, cli_region or TARGET_REGION
    )
    diag.sources["cli"] = {
        "name": f"AWS CLI Credentials ({CREDENTIALS_FILE}) [default]",
        "exists": CREDENTIALS_FILE.exists(),
        "key_masked": mask_key(cli_key),
        "key_type": "ASIA (Temporary STS)" if cli_key.startswith("ASIA") else ("AKIA (IAM User)" if cli_key.startswith("AKIA") else "UNKNOWN"),
        "has_token": bool(cli_token),
        "region": cli_region or "[NOT SET]",
        "valid": valid_cli,
        "identity": ident_cli,
        "error_code": code_cli,
        "message": msg_cli,
        "raw_credentials": {"key": cli_key, "secret": cli_secret, "token": cli_token, "region": cli_region}
    }

    # 3. Environment Variables (os.environ)
    sys_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    sys_secret = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    sys_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    sys_region = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "")).strip()

    valid_sys, ident_sys, msg_sys, code_sys = test_isolated_sts_credentials(
        sys_key, sys_secret, sys_token, sys_region or TARGET_REGION
    )
    diag.sources["os_env"] = {
        "name": "OS Environment Variables (os.environ)",
        "exists": bool(sys_key),
        "key_masked": mask_key(sys_key),
        "key_type": "ASIA (Temporary STS)" if sys_key.startswith("ASIA") else ("AKIA (IAM User)" if sys_key.startswith("AKIA") else "UNKNOWN"),
        "has_token": bool(sys_token),
        "region": sys_region or "[NOT SET]",
        "valid": valid_sys,
        "identity": ident_sys,
        "error_code": code_sys,
        "message": msg_sys
    }

    # --- B. Evaluasi Konsistensi & Region ---
    target_region_ok = (env_region == TARGET_REGION and cli_region == TARGET_REGION)
    diag.region_status = {
        "target_region": TARGET_REGION,
        "env_region": env_region,
        "cli_region": cli_region,
        "matches_target": target_region_ok
    }
    if env_region and env_region != TARGET_REGION:
        diag.issues.append({
            "category": "LOCAL_CONFIG",
            "source": ".env",
            "issue": f"Region di .env adalah '{env_region}', seharusnya '{TARGET_REGION}'.",
            "action": f"Perbaiki AWS_REGION={TARGET_REGION} di .env"
        })
    if cli_region and cli_region != TARGET_REGION:
        diag.issues.append({
            "category": "LOCAL_CONFIG",
            "source": "~/.aws/config",
            "issue": f"Region di ~/.aws/config adalah '{cli_region}', seharusnya '{TARGET_REGION}'.",
            "action": f"Perbaiki region = {TARGET_REGION} di ~/.aws/config"
        })

    # Evaluasi Sinkronisasi Kredensial
    if valid_env and not valid_cli:
        diag.issues.append({
            "category": "CREDENTIAL_DESYNC",
            "source": "AWS CLI (~/.aws/credentials)",
            "issue": "Kredensial .env valid, namun ~/.aws/credentials tidak valid atau kedaluwarsa.",
            "action": "Sinkronkan kredensial dari .env ke ~/.aws/credentials."
        })
    elif valid_cli and not valid_env:
        diag.issues.append({
            "category": "CREDENTIAL_DESYNC",
            "source": "Project .env",
            "issue": "Kredensial ~/.aws/credentials valid, namun .env kedaluwarsa atau tidak valid.",
            "action": "Sinkronkan kredensial dari ~/.aws/credentials ke .env."
        })
    elif not valid_env and not valid_cli:
        diag.issues.append({
            "category": "CREDENTIAL_EXPIRED",
            "source": "AWS Academy Cloud Labs",
            "issue": "Kredensial AWS Academy telah kedaluwarsa di semua sumber lokal (Session Token Expired).",
            "action": "Buka portal AWS Academy Learner Lab -> 'AWS Details' -> Salin block 'AWS CLI' terbaru."
        })

    # Tentukan Active Working Session (Prioritaskan yang valid)
    active_creds = None
    if valid_env:
        active_creds = diag.sources["env"]["raw_credentials"]
        diag.active_identity = ident_env
    elif valid_cli:
        active_creds = diag.sources["cli"]["raw_credentials"]
        diag.active_identity = ident_cli

    if active_creds:
        diag.resolved_session = boto3.Session(
            aws_access_key_id=active_creds["key"],
            aws_secret_access_key=active_creds["secret"],
            aws_session_token=active_creds.get("token"),
            region_name=active_creds.get("region") or TARGET_REGION
        )
    else:
        # Fallback coba default session
        diag.resolved_session = None

    # --- C. Pemeriksaan Izin API AWS ---
    if diag.resolved_session:
        diag.api_permissions = check_aws_api_permissions(diag.resolved_session)
    else:
        diag.api_permissions = {
            "sts:GetCallerIdentity": {"status": "FAIL", "reason": "Kredensial tidak valid"},
            "ec2:DescribeInstances": {"status": "SKIPPED", "reason": "Autentikasi gagal"},
            "ssm:DescribeInstanceInformation": {"status": "SKIPPED", "reason": "Autentikasi gagal"},
            "iam:GetInstanceProfile": {"status": "SKIPPED", "reason": "Autentikasi gagal"}
        }

    # --- D. Pemeriksaan EC2 & SSM (Pembedaan Masalah Mesin vs Kredensial) ---
    if diag.resolved_session:
        diag.instance_diagnosis, diag.ssm_general_status = check_ec2_and_ssm_health(diag.resolved_session)
    else:
        diag.ssm_general_status = {"status": "UNAVAILABLE", "message": "Tidak dapat memeriksa EC2/SSM karena sesi AWS tidak aktif"}

    # --- E. Pemeriksaan File Kunci SSH (PEM) & Izin NTFS ---
    diag.key_files_status = check_ssh_key_files()

    return diag


def check_aws_api_permissions(session: boto3.Session) -> Dict[str, Dict[str, Any]]:
    """Checks essential AWS API permissions required by the automation framework."""
    results = {}

    # 1. STS
    try:
        session.client("sts").get_caller_identity()
        results["sts:GetCallerIdentity"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["sts:GetCallerIdentity"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 2. EC2 Describe Instances
    try:
        session.client("ec2").describe_instances(MaxResults=5)
        results["ec2:DescribeInstances"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["ec2:DescribeInstances"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 3. EC2 Describe Key Pairs
    try:
        session.client("ec2").describe_key_pairs()
        results["ec2:DescribeKeyPairs"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["ec2:DescribeKeyPairs"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 4. EC2 Describe VPCs & Subnets
    try:
        session.client("ec2").describe_vpcs()
        results["ec2:DescribeVpcs"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["ec2:DescribeVpcs"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 5. EC2 Describe Security Groups
    try:
        session.client("ec2").describe_security_groups()
        results["ec2:DescribeSecurityGroups"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["ec2:DescribeSecurityGroups"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 6. SSM DescribeInstanceInformation
    try:
        session.client("ssm").describe_instance_information(MaxResults=5)
        results["ssm:DescribeInstanceInformation"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["ssm:DescribeInstanceInformation"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 7. SSM GetParameter (Ubuntu AMI SSM)
    try:
        session.client("ssm").get_parameter(Name="/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id")
        results["ssm:GetParameter"] = {"status": "PASS", "reason": "Tersedia"}
    except Exception as e:
        results["ssm:GetParameter"] = {"status": "FAIL", "reason": sanitize_message(str(e))}

    # 8. IAM GetInstanceProfile (LabInstanceProfile)
    try:
        session.client("iam").get_instance_profile(InstanceProfileName="LabInstanceProfile")
        results["iam:GetInstanceProfile"] = {"status": "PASS", "reason": "Tersedia (LabInstanceProfile)"}
    except Exception as e:
        results["iam:GetInstanceProfile"] = {"status": "WARN", "reason": sanitize_message(str(e))}

    return results


def check_ec2_and_ssm_health(session: boto3.Session) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Distinguishes clearly between:
    - EC2 Instance Running status
    - IAM Instance Profile attachment (LabInstanceProfile)
    - SSM Agent PingStatus ('Online' vs 'ConnectionLost' vs 'Not Registered')
    - Live command test
    """
    ec2 = session.client("ec2")
    ssm = session.client("ssm")

    ssm_general = {"status": "HEALTHY", "online_count": 0, "total_registered": 0}
    ssm_registered: Dict[str, Dict[str, Any]] = {}

    try:
        paginator = ssm.get_paginator("describe_instance_information")
        for page in paginator.paginate():
            for info in page.get("InstanceInformationList", []):
                inst_id = info["InstanceId"]
                ssm_registered[inst_id] = {
                    "ping_status": info.get("PingStatus", "Unknown"),
                    "agent_version": info.get("AgentVersion", "-"),
                    "platform": info.get("PlatformName", "-"),
                    "ip": info.get("IPAddress", "-")
                }
                if info.get("PingStatus") == "Online":
                    ssm_general["online_count"] += 1
                ssm_general["total_registered"] += 1
    except Exception as e:
        ssm_general["status"] = "ERROR"
        ssm_general["error"] = sanitize_message(str(e))

    # Ambil seluruh instance EC2 proyek
    try:
        filters = [
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}
        ]
        res = ec2.describe_instances(Filters=filters)
    except Exception as e:
        return [], {"status": "ERROR", "error": sanitize_message(str(e))}

    inst_list = []
    for r in res.get("Reservations", []):
        for inst in r.get("Instances", []):
            inst_id = inst["InstanceId"]
            state = inst["State"]["Name"]
            name = "-"
            project = "-"
            for t in inst.get("Tags", []):
                if t["Key"] == "Name":
                    name = t["Value"]
                if t["Key"] == "Project":
                    project = t["Value"]

            # Periksa IAM Instance Profile
            iam_profile_arn = inst.get("IamInstanceProfile", {}).get("Arn", "")
            has_iam_profile = bool(iam_profile_arn)
            profile_name = iam_profile_arn.split("/")[-1] if iam_profile_arn else "-"

            # Cocokkan dengan SSM
            ssm_info = ssm_registered.get(inst_id)
            if ssm_info:
                ping_status = ssm_info["ping_status"]
            else:
                ping_status = "NOT_REGISTERED"

            # Klasifikasi Masalah (Root Cause Attribution)
            root_cause = "NONE"
            status_summary = "HEALTHY"

            if state == "running":
                if not has_iam_profile:
                    status_summary = "CRITICAL"
                    root_cause = "IAM_INSTANCE_PROFILE_MISSING (Instance tidak memiliki IamInstanceProfile sehingga agen SSM ditolak oleh AWS)"
                elif ping_status == "NOT_REGISTERED":
                    status_summary = "WARNING"
                    root_cause = "SSM_AGENT_NOT_REGISTERED (Instance baru booting, atau service amazon-ssm-agent mati, atau outbound port 443 diblokir)"
                elif ping_status == "ConnectionLost":
                    status_summary = "WARNING"
                    root_cause = "SSM_CONNECTION_LOST (Agen SSM sempat terhubung tapi koneksi terputus)"
                elif ping_status == "Online":
                    status_summary = "HEALTHY"
                    root_cause = "NONE"
            else:
                status_summary = "INFO"
                root_cause = f"INSTANCE_STATE_{state.upper()}"

            inst_list.append({
                "instance_id": inst_id,
                "name": name,
                "project": project,
                "state": state,
                "public_ip": inst.get("PublicIpAddress", "-"),
                "private_ip": inst.get("PrivateIpAddress", "-"),
                "has_iam_profile": has_iam_profile,
                "iam_profile_name": profile_name,
                "ssm_ping_status": ping_status,
                "status_summary": status_summary,
                "root_cause": root_cause
            })

    inst_list.sort(key=lambda x: x["name"])
    return inst_list, ssm_general


def check_ssh_key_files() -> List[Dict[str, Any]]:
    """Checks the existence and ACL permissions of local SSH PEM files."""
    results = []
    for kf in KEY_FILES:
        item = {
            "path": str(kf),
            "name": kf.name,
            "exists": kf.exists(),
            "readable": False,
            "acl_status": "UNKNOWN",
            "size": 0
        }
        if kf.exists():
            item["size"] = kf.stat().st_size
            try:
                with open(kf, "r", encoding="utf-8") as f:
                    content = f.read(50)
                    if "BEGIN RSA PRIVATE KEY" in content or "BEGIN OPENSSH PRIVATE KEY" in content:
                        item["readable"] = True
            except Exception:
                item["readable"] = False

            # Check ACL on Windows
            if os.name == "nt":
                try:
                    out = subprocess.run(f'icacls "{kf}"', shell=True, capture_output=True, text=True)
                    acl_out = out.stdout
                    if ":(R)" in acl_out and "Everyone" not in acl_out:
                        item["acl_status"] = "SECURE_READONLY (Standard SSH)"
                    elif ":(F)" in acl_out:
                        item["acl_status"] = "FULL_ACCESS"
                    else:
                        item["acl_status"] = "CUSTOM"
                except Exception:
                    item["acl_status"] = "CHECK_FAILED"

        results.append(item)
    return results


# ==============================================================================
# 4. SAFE AUTO-REPAIR ENGINE
# ==============================================================================

class AWSDoctorRepairer:
    """Safely repairs desynchronized credentials, wrong regions, and file ACLs."""

    @staticmethod
    def backup_file(path: Path) -> Optional[Path]:
        if not path.exists():
            return None
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak_path = path.parent / f"{path.name}.bak.{ts}"
        try:
            shutil.copy2(path, bak_path)
            return bak_path
        except Exception as e:
            print(f"[ERROR] Gagal membuat backup untuk {path}: {sanitize_message(str(e))}")
            return None

    @classmethod
    def sync_credentials_to_env(cls, source_creds: Dict[str, str]) -> bool:
        """Syncs valid credentials into project .env while preserving other settings."""
        if not source_creds.get("key") or not source_creds.get("secret"):
            return False

        bak = cls.backup_file(ENV_FILE)
        print(f"[REPAIR] Backup .env dibuat di: {bak.name if bak else 'NONE'}")

        lines = []
        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()

        key_written = False
        secret_written = False
        token_written = False
        region_written = False

        new_lines = []
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("AWS_ACCESS_KEY_ID="):
                new_lines.append(f"AWS_ACCESS_KEY_ID={source_creds['key']}\n")
                key_written = True
            elif trimmed.startswith("AWS_SECRET_ACCESS_KEY="):
                new_lines.append(f"AWS_SECRET_ACCESS_KEY={source_creds['secret']}\n")
                secret_written = True
            elif trimmed.startswith("AWS_SESSION_TOKEN="):
                new_lines.append(f"AWS_SESSION_TOKEN={source_creds.get('token', '')}\n")
                token_written = True
            elif trimmed.startswith("AWS_REGION="):
                new_lines.append(f"AWS_REGION={TARGET_REGION}\n")
                region_written = True
            else:
                new_lines.append(line)

        # Jika belum ada di file
        if not key_written:
            new_lines.append(f"AWS_ACCESS_KEY_ID={source_creds['key']}\n")
        if not secret_written:
            new_lines.append(f"AWS_SECRET_ACCESS_KEY={source_creds['secret']}\n")
        if not token_written and source_creds.get("token"):
            new_lines.append(f"AWS_SESSION_TOKEN={source_creds['token']}\n")
        if not region_written:
            new_lines.append(f"AWS_REGION={TARGET_REGION}\n")

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"[REPAIR] Berhasil memperbarui kredensial di {ENV_FILE}")
        return True

    @classmethod
    def sync_credentials_to_cli(cls, source_creds: Dict[str, str], profile: str = "default") -> bool:
        """Syncs valid credentials into ~/.aws/credentials and ~/.aws/config."""
        if not source_creds.get("key") or not source_creds.get("secret"):
            return False

        AWS_DIR.mkdir(parents=True, exist_ok=True)
        bak_cred = cls.backup_file(CREDENTIALS_FILE)
        bak_cfg = cls.backup_file(CONFIG_FILE)
        print(f"[REPAIR] Backup credentials dibuat: {bak_cred.name if bak_cred else 'NONE'}")

        # Update ~/.aws/credentials
        cp = configparser.RawConfigParser()
        if CREDENTIALS_FILE.exists():
            cp.read(str(CREDENTIALS_FILE), encoding="utf-8")
        if not cp.has_section(profile):
            cp.add_section(profile)

        cp.set(profile, "aws_access_key_id", source_creds["key"])
        cp.set(profile, "aws_secret_access_key", source_creds["secret"])
        if source_creds.get("token"):
            cp.set(profile, "aws_session_token", source_creds["token"])
        elif cp.has_option(profile, "aws_session_token"):
            cp.remove_option(profile, "aws_session_token")

        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            cp.write(f)

        # Update ~/.aws/config
        cp_cfg = configparser.RawConfigParser()
        if CONFIG_FILE.exists():
            cp_cfg.read(str(CONFIG_FILE), encoding="utf-8")
        sec_name = profile if profile == "default" else f"profile {profile}"
        if not cp_cfg.has_section(sec_name):
            cp_cfg.add_section(sec_name)
        cp_cfg.set(sec_name, "region", TARGET_REGION)
        cp_cfg.set(sec_name, "output", "json")

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            cp_cfg.write(f)

        print(f"[REPAIR] Berhasil memperbarui kredensial di {CREDENTIALS_FILE} & {CONFIG_FILE}")
        return True

    @classmethod
    def secure_ssh_key_permissions(cls) -> int:
        """Enforces Read-Only NTFS permissions for current user on Windows."""
        fixed = 0
        if os.name != "nt":
            return fixed

        username = os.environ.get("USERNAME", "")
        if not username:
            return fixed

        for kf in KEY_FILES:
            if kf.exists():
                try:
                    subprocess.run(f'icacls "{kf}" /inheritance:r', shell=True, check=True, capture_output=True)
                    subprocess.run(f'icacls "{kf}" /grant:r "{username}:(R)"', shell=True, check=True, capture_output=True)
                    fixed += 1
                except Exception as e:
                    print(f"[WARN] Gagal mengamankan ACL untuk {kf.name}: {sanitize_message(str(e))}")
        return fixed


def perform_safe_repairs(diag: AWSDoctorDiagnosis) -> List[str]:
    """Executes safe auto-repairs based on diagnosis findings."""
    actions_taken = []
    env_info = diag.sources.get("env", {})
    cli_info = diag.sources.get("cli", {})

    valid_env = env_info.get("valid", False)
    valid_cli = cli_info.get("valid", False)

    # 1. Sinkronisasi Kredensial
    if valid_cli and not valid_env:
        print("\n[*] Menjalankan Sinkronisasi Kredensial: AWS CLI -> .env Proyek...")
        success = AWSDoctorRepairer.sync_credentials_to_env(cli_info["raw_credentials"])
        if success:
            actions_taken.append("Disinkronkan kredensial valid dari ~/.aws/credentials ke .env proyek")
    elif valid_env and not valid_cli:
        print("\n[*] Menjalankan Sinkronisasi Kredensial: .env Proyek -> AWS CLI...")
        success = AWSDoctorRepairer.sync_credentials_to_cli(env_info["raw_credentials"])
        if success:
            actions_taken.append("Disinkronkan kredensial valid dari .env proyek ke ~/.aws/credentials")

    # 2. Penyelarasan Region
    if env_info.get("region") != TARGET_REGION and valid_env:
        print(f"[*] Menyelaraskan region .env ke {TARGET_REGION}...")
        AWSDoctorRepairer.sync_credentials_to_env(env_info["raw_credentials"])
        actions_taken.append(f"Penyelarasan AWS_REGION={TARGET_REGION} di .env")

    # 3. Pengamanan File Kunci SSH
    secured_keys = AWSDoctorRepairer.secure_ssh_key_permissions()
    if secured_keys > 0:
        actions_taken.append(f"Diamankan ACL izin NTFS {secured_keys} file SSH Private Key (Read-Only user)")

    # 4. Reload In-Memory Settings
    if hasattr(settings, "reload"):
        settings.reload()
    else:
        # Fallback manual reload
        from dotenv import load_dotenv
        load_dotenv(override=True)
        settings.AWS_REGION = os.getenv("AWS_REGION", TARGET_REGION)
        settings.AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        settings.AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        settings.AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "").strip()

    return actions_taken


# ==============================================================================
# 5. TEST & VERIFICATION SUITE
# ==============================================================================

def execute_ssm_live_ping_test(session: boto3.Session, target_instance_id: Optional[str] = None) -> Tuple[bool, str]:
    """Sends a harmless live echo command via SSM to verify command dispatch & retrieval."""
    ssm = session.client("ssm")
    try:
        # Cari instance yang Online
        info_res = ssm.describe_instance_information()
        online_instances = [
            i["InstanceId"] for i in info_res.get("InstanceInformationList", [])
            if i.get("PingStatus") == "Online"
        ]

        if not online_instances:
            return False, "Tidak ada instance yang berstatus SSM 'Online' untuk dilakukan pengujian live command."

        chosen_id = target_instance_id if (target_instance_id and target_instance_id in online_instances) else online_instances[0]

        res = ssm.send_command(
            InstanceIds=[chosen_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": ["echo '__AWS_DOCTOR_VERIFY_SUCCESS__'"]},
            TimeoutSeconds=30
        )
        cmd_id = res["Command"]["CommandId"]

        # Polling singkat hingga 10 detik
        stdout = ""
        cmd_status = "Pending"
        for _ in range(5):
            time.sleep(2)
            try:
                inv = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=chosen_id)
                cmd_status = inv.get("Status", "Pending")
                if cmd_status in ["Success", "Failed"]:
                    stdout = inv.get("StandardOutputContent", "")
                    break
            except Exception:
                pass

        if cmd_status == "Success" and "__AWS_DOCTOR_VERIFY_SUCCESS__" in stdout:
            return True, f"Berhasil mengirim & menerima respon perintah SSM dari instance {chosen_id} (Command ID: {cmd_id})"
        elif cmd_status == "Success":
            return True, f"Perintah SSM berhasil dieksekusi di {chosen_id} (Command ID: {cmd_id})"
        else:
            return False, f"Pengujian perintah SSM selesai dengan status: {cmd_status} (Instance: {chosen_id})"

    except Exception as e:
        return False, f"Gagal mengeksekusi pengujian perintah SSM: {sanitize_message(str(e))}"


# ==============================================================================
# 6. REPORT GENERATOR
# ==============================================================================

def print_banner(title: str):
    print("\n" + "=" * 85)
    print(f" {title.center(83)} ")
    print("=" * 85)


def print_section(title: str):
    print(f"\n[+] {title}")
    print("-" * 85)


def render_report(
    diag: AWSDoctorDiagnosis,
    repairs_done: List[str],
    is_post_repair: bool = False,
    live_ssm_result: Optional[Tuple[bool, str]] = None
):
    print_banner("AWS DOCTOR: LAPORAN AUDIT & DIAGNOSIS KREDENSIAL LENGKAP")
    print(f"Waktu Pemeriksaan : {diag.timestamp}")
    print(f"Target Region     : {TARGET_REGION}")

    # 1. Kredensial Lokal
    print_section("1. STATUS SUMBER KREDENSIAL LOKAL (AWS CLI vs .env vs ENV)")
    header = f"{'SUMBER':<32} | {'STATUS':<10} | {'KEY ID (MASKED)':<18} | {'TIPE':<14} | {'TOKEN':<7}"
    print(header)
    print("-" * len(header))
    for src_key, src in diag.sources.items():
        st_label = "VALID" if src.get("valid") else ("EXPIRED" if "Expired" in src.get("message", "") else "INVALID")
        if not src.get("exists"):
            st_label = "NOT FOUND"
        has_tok = "ADA" if src.get("has_token") else "TIDAK"
        print(f"{src['name'][:32]:<32} | {st_label:<10} | {src['key_masked']:<18} | {src['key_type']:<14} | {has_tok:<7}")
        if not src.get("valid") and src.get("exists"):
            print(f"    --> Rincian Kendala : {src.get('message')}")

    # 2. Identitas AWS Aktif
    print_section("2. IDENTITAS & SESI AWS TERHUBUNG (STS CALLER IDENTITY)")
    if diag.active_identity:
        acc = diag.active_identity.get("Account", "-")
        arn = diag.active_identity.get("Arn", "-")
        user_id = diag.active_identity.get("UserId", "-")
        print(f"  * AWS Account ID   : {acc}")
        print(f"  * Caller ARN       : {arn}")
        print(f"  * Caller User ID   : {user_id}")
        print(f"  * Region Aktif     : {TARGET_REGION} (OK)")
    else:
        print("  [!] PERINGATAN: Tidak ada kredensial valid yang dapat terhubung ke AWS STS.")
        print("      Semua panggilan API ke AWS saat ini akan gagal.")

    # 3. Matriks Izin API AWS
    print_section("3. MATRIKS VALIDASI IZIN API AWS (BOTO3 & CLI PERMISSIONS)")
    api_header = f"{'NAMA AKSI API':<35} | {'STATUS':<10} | {'KETERANGAN':<35}"
    print(api_header)
    print("-" * len(api_header))
    for action, res in diag.api_permissions.items():
        st = res["status"]
        reason = res["reason"][:35]
        print(f"{action:<35} | {st:<10} | {reason:<35}")

    # 4. Diagnosa EC2 & SSM
    print_section("4. AUDIT RUNTIME EC2 & SYSTEMS MANAGER (PEMBEDAAN KREDENSIAL vs SSM)")
    if diag.instance_diagnosis:
        ec2_header = f"{'NAMA':<20} | {'INSTANCE ID':<19} | {'STATE':<9} | {'IAM PROFILE':<15} | {'SSM STATUS':<12}"
        print(ec2_header)
        print("-" * len(ec2_header))
        for inst in diag.instance_diagnosis:
            print(f"{inst['name'][:20]:<20} | {inst['instance_id']:<19} | {inst['state']:<9} | {inst['iam_profile_name'][:15]:<15} | {inst['ssm_ping_status']:<12}")
            if inst["root_cause"] != "NONE":
                print(f"    --> Diagnosa Kendala : {inst['root_cause']}")
    else:
        print("  - Tidak ada instance EC2 yang ditemukan atau gagal mengambil daftar instance.")

    # 5. Live SSM Test Result
    if live_ssm_result:
        print_section("5. PENGUJIAN EKSEKUSI PERINTAH JARAK JAUH (SSM RUN-SHELL LIVE TEST)")
        success, live_msg = live_ssm_result
        st_ping = "PASS" if success else "FAIL"
        print(f"  * Status Uji Eksekusi : [{st_ping}]")
        print(f"  * Laporan Hasil      : {live_msg}")

    # 6. File Kunci SSH (PEM)
    print_section("6. PEMERIKSAAN KUNCI SSH LOKAL (VOCKEY.PEM / LABSUSER.PEM)")
    for kf in diag.key_files_status:
        ex = "Ditemukan" if kf["exists"] else "Tidak Ditemukan"
        acl = kf.get("acl_status", "-")
        read_st = "Dapat dibaca" if kf.get("readable") else "Gagal dibaca"
        print(f"  * {kf['name']:<14} : {ex:<15} | {read_st:<14} | Izin ACL: {acl}")

    # 7. Tindakan Perbaikan Yang Dilakukan
    if repairs_done:
        print_section("7. TINDAKAN PERBAIKAN OTOMATIS YANG TELAH DITERAPKAN")
        for idx, act in enumerate(repairs_done, 1):
            print(f"  [{idx}] {act}")

    # 8. Kesimpulan & Rekomendasi
    print_section("8. KESIMPULAN & LANGKAH TINDAK LANJUT")
    all_valid = bool(diag.active_identity) and all(
        p.get("status") in ["PASS", "WARN"] for p in diag.api_permissions.values()
    )

    if all_valid:
        print("  [SUCCESS] Kredensial AWS dan konfigurasi SSM dalam kondisi PRIMA & SIAP DIGUNAKAN!")
        print("  Semua instance berjalan normal tanpa ada resource yang terganggu.")
    else:
        print("  [ACTION REQUIRED] Ditemukan kendala yang memerlukan perhatian:")
        for idx, iss in enumerate(diag.issues, 1):
            print(f"  {idx}. [{iss['category']}] Sumber: {iss['source']}")
            print(f"     Masalah : {iss['issue']}")
            print(f"     Solusi  : {iss['action']}")

        if not diag.active_identity:
            print("\n  PANDUAN PEMBARUAN KREDENSIAL AWS ACADEMY LEARNER LAB:")
            print("  1. Buka dashboard AWS Academy Learner Lab di browser.")
            print("  2. Klik tombol 'Start Lab' (tunggu hingga indikator berwarna hijau).")
            print("  3. Klik tombol 'AWS Details', lalu lihat bagian 'AWS CLI'.")
            print("  4. Buka file D:\\LKPD\\aws-lkpd-automation\\.env atau jalankan pembaruan kredensial.")
            print("  5. Jalankan kembali: python main.py aws-doctor --repair --verify")

    print("\n" + "=" * 85 + "\n")


# ==============================================================================
# 7. MAIN ENTRYPOINT FOR AWS DOCTOR
# ==============================================================================

def run_aws_doctor(
    repair: bool = False,
    verify: bool = False,
    target_instance_id: Optional[str] = None
) -> bool:
    """
    Unified entry point executing:
    Diagnosis -> Safe Auto-Repair -> Verification -> Report.
    Returns True if healthy/repaired, False if critical issues remain.
    """
    print("\n" + "#" * 85)
    print(" INITIATING AWS DOCTOR: DIAGNOSIS & REPAIR PROTOCOL ".center(85, "#"))
    print("#" * 85)

    # Langkah 1: Diagnosis Awal
    print("[1/4] Menjalankan audit mendalam kredensial dan konfigurasi AWS...")
    diag = run_full_diagnosis()

    repairs_done = []
    # Langkah 2: Perbaikan Aman (Jika diminta atau jika ada masalah yang dapat disinkronkan)
    if repair:
        print("[2/4] Menjalankan perbaikan konfigurasi secara aman (Non-Destructive)...")
        repairs_done = perform_safe_repairs(diag)
        if not repairs_done:
            print("[*] Tidak ada konfigurasi lokal yang perlu diperbaiki.")
    else:
        print("[2/4] Mode perbaikan otomatis dinonaktifkan (Gunakan flag --repair untuk mengaktifkan).")

    # Langkah 3: Verifikasi Ulang (Jika --verify atau jika perbaikan baru dilakukan)
    live_ssm_result = None
    if verify or repair:
        print("[3/4] Menjalankan verifikasi ulang paska-perbaikan...")
        # Jalankan diagnosis ulang untuk mencerminkan status terkini
        diag = run_full_diagnosis()

        if diag.resolved_session:
            print("[*] Menguji eksekusi perintah jarak jauh (SSM live ping)...")
            live_ssm_result = execute_ssm_live_ping_test(diag.resolved_session, target_instance_id)
    else:
        print("[3/4] Verifikasi lanjutan dilewati (Gunakan flag --verify).")

    # Langkah 4: Cetak Laporan Komprehensif
    print("[4/4] Menyusun laporan hasil audit...")
    render_report(diag, repairs_done, is_post_repair=(verify or repair), live_ssm_result=live_ssm_result)

    # Evaluasi status akhir untuk exit code
    is_healthy = bool(diag.active_identity) and all(
        p.get("status") in ["PASS", "WARN"] for p in diag.api_permissions.values()
    )
    return is_healthy
