from lkpd.base import BaseLKPD

class Tugas2(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=2, name="tugas-2-idcard", main_port=8080)
        self.task_type = "tugas2"
        self.instance_name = "tugas-2-idcard"

    def get_user_data_script(self) -> str:
        return self.render_script("tugas2_idcard.sh")
