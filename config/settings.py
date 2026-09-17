import os
from typing import List, Tuple
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # AWS
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '').strip()
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '').strip()
    AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN', '').strip()

    # EC2
    EC2_AMI_ID = os.getenv('EC2_AMI_ID', '').strip()
    EC2_AMI_ARCHITECTURE = os.getenv('EC2_AMI_ARCHITECTURE', 'x86_64').strip()
    EC2_INSTANCE_TYPE = os.getenv('EC2_INSTANCE_TYPE', 't3.small').strip()
    EC2_KEY_NAME = os.getenv('EC2_KEY_NAME', 'vockey').strip()
    EC2_IAM_INSTANCE_PROFILE = os.getenv('EC2_IAM_INSTANCE_PROFILE', 'lab instance profile').strip()

    # Network
    VPC_ID = os.getenv('VPC_ID', '').strip()
    SUBNET_ID = os.getenv('SUBNET_ID', '').strip()
    SECURITY_GROUP_ID = os.getenv('SECURITY_GROUP_ID', '').strip()
    SECURITY_GROUP_NAME = os.getenv('SECURITY_GROUP_NAME', 'sg-lkpd-docker').strip()

    # SG Rules
    SG_RULES_RAW = os.getenv('SG_RULES', '22:0.0.0.0/0,80:0.0.0.0/0,443:0.0.0.0/0,7070:0.0.0.0/0,8080:0.0.0.0/0,8001:0.0.0.0/0,8002:0.0.0.0/0,8088:0.0.0.0/0,3306:0.0.0.0/0').strip()

    # Project
    PROJECT_NAME = os.getenv('PROJECT_NAME', 'aws-lkpd-automation').strip()
    KEEP_INSTANCES = os.getenv('KEEP_INSTANCES', 'true').strip().lower() in ('true', '1', 'yes')

    # LKPD 2 App
    APP_REPOSITORY = os.getenv('APP_REPOSITORY', 'https://github.com/paknux/apptoko.git').strip()
    APP_BRANCH = os.getenv('APP_BRANCH', '').strip()

    # LKPD 4 Docker Hub
    DOCKERHUB_USERNAME = os.getenv('DOCKERHUB_USERNAME', '').strip()
    DOCKERHUB_TOKEN = os.getenv('DOCKERHUB_TOKEN', '').strip()
    DOCKERHUB_REPOSITORY = os.getenv('DOCKERHUB_REPOSITORY', 'ubuntu-ws').strip()
    DOCKERHUB_TAG = os.getenv('DOCKERHUB_TAG', 'v1').strip()
    DOCKERHUB_SKIP_PUSH = os.getenv('DOCKERHUB_SKIP_PUSH', 'false').strip().lower() in ('true', '1', 'yes')

    # Timeouts
    INSTANCE_TIMEOUT_SECONDS = int(os.getenv('INSTANCE_TIMEOUT_SECONDS', '600'))
    WORKFLOW_TIMEOUT_SECONDS = int(os.getenv('WORKFLOW_TIMEOUT_SECONDS', '1800'))

    @classmethod
    def parse_sg_rules(cls) -> List[Tuple[int, str]]:
        rules = []
        parts = [p.strip() for p in cls.SG_RULES_RAW.split(',') if p.strip()]
        for item in parts:
            if ':' in item:
                port_str, cidr = item.split(':', 1)
                rules.append((int(port_str.strip()), cidr.strip()))
        return rules

settings = Settings()
