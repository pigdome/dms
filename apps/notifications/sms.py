"""
SMS Service abstraction สำหรับส่ง SMS ผ่าน ThaiBulkSMS (หรือ generic HTTP SMS provider).
ออกแบบให้ degrade gracefully — ถ้าไม่มี credentials ให้ log warning แล้วคืน False
โดยไม่ crash เพื่อให้ระบบยังทำงานต่อได้
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Endpoint เริ่มต้นของ ThaiBulkSMS — สามารถ override ได้ใน settings.py
SMS_API_URL = getattr(settings, 'SMS_API_URL', 'https://www.thaibulksms.com/api/sms/send')


class SMSService:
    """
    Wrapper สำหรับ HTTP call ไปยัง SMS provider (ThaiBulkSMS).

    ใช้งาน:
        sms = SMSService(api_key='xxx', sender_name='DORM')
        sent = sms.send_sms(phone='0812345678', message='ค่าเช่าเดือนนี้ครบกำหนดแล้ว')
    """

    def __init__(self, api_key: str = '', sender_name: str = ''):
        # ถ้าไม่ส่ง credentials มา ให้ fallback ไปอ่านจาก settings
        self.api_key = api_key or getattr(settings, 'SMS_API_KEY', '')
        self.sender_name = sender_name or getattr(settings, 'SMS_SENDER_NAME', '')
        self.api_url = SMS_API_URL

    def send_sms(self, phone: str, message: str) -> bool:
        """
        ส่ง SMS ไปยังหมายเลข phone พร้อมข้อความ message.
        คืน True ถ้าส่งสำเร็จ, False ถ้าล้มเหลวหรือไม่มี credentials.

        Graceful degrade: ถ้าไม่มี api_key → log warning แล้วคืน False
        """
        if not self.api_key:
            logger.warning(
                'SMS api_key ไม่ได้กำหนด — ข้ามการส่ง SMS ไปยัง %s',
                phone,
            )
            return False

        if not phone:
            logger.warning('SMS phone number ว่างเปล่า — ข้ามการส่ง')
            return False

        # ปรับหมายเลขโทรศัพท์ไทย: แปลง 08x → +668x
        normalized_phone = self._normalize_phone(phone)

        payload = {
            'key': self.api_key,
            'msisdn': normalized_phone,
            'message': message,
            'sender': self.sender_name,
        }

        try:
            resp = requests.post(self.api_url, data=payload, timeout=10)
            resp.raise_for_status()
            # ThaiBulkSMS คืน status code 200 เมื่อส่งสำเร็จ
            logger.info(
                'SMS ส่งสำเร็จ → %s (status=%s)',
                normalized_phone,
                resp.status_code,
            )
            return True
        except requests.exceptions.Timeout:
            logger.error('SMS timeout ขณะส่งไปยัง %s', normalized_phone)
            return False
        except requests.exceptions.HTTPError as exc:
            logger.error(
                'SMS HTTP error %s ขณะส่งไปยัง %s: %s',
                exc.response.status_code if exc.response else '?',
                normalized_phone,
                exc,
            )
            return False
        except requests.exceptions.RequestException as exc:
            logger.error('SMS request error ขณะส่งไปยัง %s: %s', normalized_phone, exc)
            return False

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """
        แปลงหมายเลขโทรศัพท์ไทยให้อยู่ในรูป E.164 (+66xxx).
        รับได้ทั้ง 08xxxxxxxx, 668xxxxxxxx, +668xxxxxxxx
        """
        phone = phone.strip().replace('-', '').replace(' ', '')
        if phone.startswith('+66'):
            return phone
        if phone.startswith('66'):
            return f'+{phone}'
        if phone.startswith('0'):
            return f'+66{phone[1:]}'
        return phone
