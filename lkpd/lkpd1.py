from lkpd.base import BaseLKPD

class LKPD1(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=1, name="docker-http", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd1.sh")
