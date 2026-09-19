from backend import models, scheduler
from backend.db import SessionLocal, init_db


def test_scheduler_recovers_persisted_push_time_after_restart():
    # 其他 API 测试会清理共享临时库；此处显式建表以验证“重启后读取设置”。
    init_db()
    db = SessionLocal()
    try:
        setting = db.query(models.Settings).first()
        if setting is None:
            setting = models.Settings(email="", push_time="08:30", ebbinghaus_steps="1,2,4,7,15,30,60")
            db.add(setting)
        else:
            setting.push_time = "08:30"
        db.commit()
        assert scheduler._configured_push_time() == (8, 30)

        setting.push_time = "not-a-time"
        db.commit()
        assert scheduler._configured_push_time() == (9, 0)
    finally:
        # 不把故意写入的非法值泄漏到共享测试库。
        if db.is_active:
            current = db.query(models.Settings).first()
            if current:
                current.push_time = "09:00"
                db.commit()
        db.close()
