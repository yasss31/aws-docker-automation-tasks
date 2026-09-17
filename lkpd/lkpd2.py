from lkpd.base import BaseLKPD
from config.settings import settings

class LKPD2(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=2, name="multi-container", main_port=8088)

    def get_user_data_script(self) -> str:
        env = {
            "APP_REPOSITORY": settings.APP_REPOSITORY,
            "APP_BRANCH": settings.APP_BRANCH
        }
        return self.render_script("lkpd2.sh", extra_env=env)
