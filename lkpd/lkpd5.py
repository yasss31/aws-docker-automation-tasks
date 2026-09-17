from lkpd.base import BaseLKPD

class LKPD5(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=5, name="compose", main_port=8088)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd5.sh")
