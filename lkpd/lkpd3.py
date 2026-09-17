from lkpd.base import BaseLKPD

class LKPD3(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=3, name="dockerfile", main_port=8001)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd3.sh")
