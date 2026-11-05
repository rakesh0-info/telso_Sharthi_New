from concurrent.futures import ThreadPoolExecutor

from mail.sendmail import send_school_admin_welcome_email


def send_welcome_emails_background(
    admin_list: list[dict], school_info: dict
):
  with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(send_school_admin_welcome_email, admin, school_info)
        for admin in admin_list
    ]
    # Wait for all background emails to finish dispatching
    for future in futures:
      future.result()