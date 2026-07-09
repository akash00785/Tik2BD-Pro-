import logging
import sys

def get_logger(name="Tik2BD-Pro"):
    """
    প্রফেশনাল লগিং কনফিগারেশন।
    এটি কনসোলে লগ প্রিন্ট করবে যা রেন্ডার বা যেকোনো ক্লাউড প্ল্যাটফর্মে দেখা যাবে।
    """
    logger = logging.getLogger(name)
    
    # যদি আগে থেকে হ্যান্ডলার থাকে, তবে নতুন করে যোগ করার দরকার নেই
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # ফরম্যাট তৈরি
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # স্ট্রীম হ্যান্ডলার (কনসোলে আউটপুট দেখার জন্য)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        
    return logger

# একটি গ্লোবাল লগার অবজেক্ট তৈরি করে রাখা হলো
logger = get_logger()

