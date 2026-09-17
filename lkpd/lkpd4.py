from lkpd.base import BaseLKPD
from config.settings import settings

class LKPD4(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=4, name="dockerhub", main_port=8002)

    def get_user_data_script(self) -> str:
        env = {
            "DOCKERHUB_USERNAME": settings.DOCKERHUB_USERNAME,
            "DOCKERHUB_TOKEN": settings.DOCKERHUB_TOKEN,
            "DOCKERHUB_REPOSITORY": settings.DOCKERHUB_REPOSITORY,
            "DOCKERHUB_TAG": settings.DOCKERHUB_TAG,
            "DOCKERHUB_SKIP_PUSH": "true" if settings.DOCKERHUB_SKIP_PUSH else "false"
        }
        return self.render_script("lkpd4.sh", extra_env=env)
