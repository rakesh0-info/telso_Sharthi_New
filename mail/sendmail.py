from email.message import EmailMessage
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv



load_dotenv()

# Read the configurations safely
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip() # Fallback to default if missing
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))             # Convert port to integer
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD") 


def send_mail(receiver_mail: str, otp: str):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = receiver_mail
    msg["Subject"] = "Your Verification OTP"
    
    body_content = f"This is your OTP: {otp}. It will expire in 5 minutes."
    msg.attach(MIMEText(body_content, "plain"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print("Error sending mail: ", e)



def send_teacher_welcome_email(to_email: str, teacher_name: str, temp_password: str, school_obj):
    smtp_host = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    sender_email = os.getenv("SENDER_EMAIL") or os.getenv("SMTP_USER")
    sender_password = os.getenv("SMTP_PASSWORD")

    msg = EmailMessage()
    msg['Subject'] = f"Welcome to {school_obj.school_name} - Telso Sharthi Credentials"
    msg['From'] = sender_email
    msg['To'] = to_email

    msg.set_content(f"""
Hello {teacher_name},

Your teacher account has been successfully created for {school_obj.school_name}.

--- School Information ---
• School Name: {school_obj.school_name}
• School Code: {school_obj.School_Code}
• District: {school_obj.District}
• Region: {school_obj.Region}
• Address: {school_obj.address or 'N/A'}
• Phone: {school_obj.phone or 'N/A'}

--- Your Login Credentials ---
Email: {to_email}
Temporary Password: {temp_password}

Please log in and update your password immediately.

Best regards,
School Administration
""")
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise RuntimeError(f"Teacher created, but email dispatch failed: {e}")


def send_LabAssistent_welcome_email(to_email: str, LabName: str, temp_password: str, school_obj):
    smtp_host = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    sender_email = os.getenv("SENDER_EMAIL") or os.getenv("SMTP_USER")
    sender_password = os.getenv("SMTP_PASSWORD")

    msg = EmailMessage()
    msg['Subject'] = f"Welcome to {school_obj.school_name} - Telso Sharthi Credentials"
    msg['From'] = sender_email
    msg['To'] = to_email

    msg.set_content(f"""
Hello {LabName},

Your Lab Assistent account has been successfully created for {school_obj.school_name}.

--- School Information ---
• School Name: {school_obj.school_name}
• School Code: {school_obj.School_Code}
• District: {school_obj.District}
• Region: {school_obj.Region}
• Address: {school_obj.address or 'N/A'}
• Phone: {school_obj.phone or 'N/A'}

--- Your Login Credentials ---
Email: {to_email}
Temporary Password: {temp_password}

Please log in and update your password immediately.

Best regards,
School Administration
""")
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise RuntimeError(f"Teacher created, but email dispatch failed: {e}")




