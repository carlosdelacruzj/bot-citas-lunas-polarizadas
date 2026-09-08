from dataclasses import dataclass


@dataclass(frozen=True)
class CaptchaSettings:
    captcha_api_key: str
    captcha_rejection_cooldown_seconds: int
    reservation_captcha_max_attempts: int
    observer_captcha_sample_limit: int
    captcha_shadow_enabled: bool
    captcha_shadow_url: str
    captcha_shadow_queue_size: int
    captcha_shadow_timeout_seconds: int
    reservation_captcha_sample_limit: int
    reservation_captcha_runtime_control_enabled: bool
    reservation_math_pre_submit_delay_min_seconds: float
    reservation_math_pre_submit_delay_max_seconds: float
