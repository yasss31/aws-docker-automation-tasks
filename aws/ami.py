import logging
import boto3
from botocore.exceptions import ClientError
from config.settings import settings

logger = logging.getLogger(__name__)

UBUNTU_2404_SSM_PARAM = '/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id'
CANONICAL_OWNER_ID = '099720109477'

def get_session():
    kwargs = {"region_name": settings.AWS_REGION}
    if settings.AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
    return boto3.Session(**kwargs)

def resolve_ubuntu_ami() -> str:
    session = get_session()
    ec2 = session.client("ec2")

    if settings.EC2_AMI_ID:
        logger.info(f"Memvalidasi AMI spesifik dari .env: {settings.EC2_AMI_ID}")
        try:
            res = ec2.describe_images(ImageIds=[settings.EC2_AMI_ID])
            if res.get("Images"):
                img = res["Images"][0]
                logger.info(f"AMI valid: {img['ImageId']} ({img.get('Name')})")
                return settings.EC2_AMI_ID
        except ClientError as e:
            raise RuntimeError(f"AMI {settings.EC2_AMI_ID} tidak valid atau tidak ditemukan di {settings.AWS_REGION}: {e}")

    logger.info("Mencari Ubuntu 24.04 LTS x86_64 via SSM Parameter Store...")
    try:
        ssm = session.client("ssm")
        param = ssm.get_parameter(Name=UBUNTU_2404_SSM_PARAM)
        ami_id = param["Parameter"]["Value"]
        logger.info(f"Ditemukan AMI via SSM: {ami_id}")
        return ami_id
    except Exception as e:
        logger.warning(f"Gagal query SSM Parameter Store ({e}), beralih ke DescribeImages filter Canonical...")

    try:
        res = ec2.describe_images(
            Owners=[CANONICAL_OWNER_ID],
            Filters=[
                {"Name": "name", "Values": ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]},
                {"Name": "state", "Values": ["available"]},
                {"Name": "architecture", "Values": [settings.EC2_AMI_ARCHITECTURE]}
            ]
        )
        images = res.get("Images", [])
        if not images:
            raise RuntimeError("Tidak ditemukan AMI Ubuntu 24.04 LTS dari Canonical di region ini.")
        images.sort(key=lambda x: x["CreationDate"], reverse=True)
        ami_id = images[0]["ImageId"]
        logger.info(f"Ditemukan AMI via DescribeImages: {ami_id} ({images[0].get('Name')})")
        return ami_id
    except ClientError as e:
        raise RuntimeError(f"Gagal mencari AMI Ubuntu: {e}")
