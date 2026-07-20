import random
import string
from datetime import datetime

class SnowflakeGenerator:
    def __init__(self, worker_id: int = 1, datacenter_id: int = 1):
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = -1
        self.worker_id_bits = 5
        self.datacenter_id_bits = 5
        self.sequence_bits = 12
        self.max_worker_id = -1 ^ (-1 << self.worker_id_bits)
        self.max_datacenter_id = -1 ^ (-1 << self.datacenter_id_bits)
        self.worker_id_shift = self.sequence_bits
        self.datacenter_id_shift = self.sequence_bits + self.worker_id_bits
        self.timestamp_left_shift = self.sequence_bits + self.worker_id_bits + self.datacenter_id_bits
        self.sequence_mask = -1 ^ (-1 << self.sequence_bits)
        
        if self.worker_id > self.max_worker_id or self.worker_id < 0:
            raise ValueError(f"worker_id must be between 0 and {self.max_worker_id}")
        if self.datacenter_id > self.max_datacenter_id or self.datacenter_id < 0:
            raise ValueError(f"datacenter_id must be between 0 and {self.max_datacenter_id}")
    
    def _get_timestamp(self):
        return int(datetime.now().timestamp() * 1000)
    
    def generate(self):
        timestamp = self._get_timestamp()
        
        if timestamp < self.last_timestamp:
            raise ValueError("Clock moved backwards")
        
        if timestamp == self.last_timestamp:
            self.sequence = (self.sequence + 1) & self.sequence_mask
            if self.sequence == 0:
                while timestamp <= self.last_timestamp:
                    timestamp = self._get_timestamp()
        else:
            self.sequence = 0
        
        self.last_timestamp = timestamp
        
        return (
            (timestamp << self.timestamp_left_shift) |
            (self.datacenter_id << self.datacenter_id_shift) |
            (self.worker_id << self.worker_id_shift) |
            self.sequence
        )

snowflake_generator = SnowflakeGenerator()

def generate_snowflake_id() -> int:
    return snowflake_generator.generate()

def generate_tenant_id() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

def generate_order_no() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"ORD{timestamp}{random_str}"

def generate_coupon_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=8))

def generate_qr_code() -> str:
    """Generate a QR code string (16 character random string for barcode usage).
    
    Returns:
        A 16-character string suitable for generating QR codes.
    """
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=16))