import os
from abc import ABC, abstractmethod
from config.settings import settings

class BaseLKPD(ABC):
    def __init__(self, lkpd_num: int, name: str, main_port: int):
        self.lkpd_num = lkpd_num
        self.name = name
        self.main_port = main_port

    @abstractmethod
    def get_user_data_script(self) -> str:
        pass

    def render_script(self, template_name: str, extra_env: dict = None) -> str:
        template_path = os.path.join(os.path.dirname(__file__), "..", "templates", template_name)
        bootstrap_path = os.path.join(os.path.dirname(__file__), "..", "templates", "bootstrap.sh")

        with open(bootstrap_path, "r", encoding="utf-8") as f:
            bootstrap_content = f.read()

        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        env_exports = []
        if extra_env:
            for k, v in extra_env.items():
                escaped_v = str(v).replace('"', '\"')
                env_exports.append(f'export {k}="{escaped_v}"')
        env_block = "\n".join(env_exports)

        # Injeksi User Data: Membuat /opt/lkpd/bootstrap.sh dulu, baru run.sh
        full_user_data = f"""#!/bin/bash
mkdir -p /opt/lkpd

cat << 'BOOTSTRAP_EOF' > /opt/lkpd/bootstrap.sh
{bootstrap_content}
BOOTSTRAP_EOF
chmod +x /opt/lkpd/bootstrap.sh

cat << 'RUNNER_EOF' > /opt/lkpd/run.sh
{env_block}
{template_content}
RUNNER_EOF
chmod +x /opt/lkpd/run.sh

/opt/lkpd/run.sh
"""
        return full_user_data
