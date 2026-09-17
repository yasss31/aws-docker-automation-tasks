from lkpd.base import BaseLKPD

class Tugas3(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=3, name="tugas-3-reservasi", main_port=8083)
        self.task_type = "tugas3"
        self.instance_name = "tugas-3-reservasi"

    def get_user_data_script(self) -> str:
        return self.render_script("tugas3_reservasi.sh")
