
def passwordCheack(password:str) -> bool:
     is_long_enough = len(password) >= 8
     has_number = any(char.isdigit() for char in password)
     has_letter = any(char.isalpha() for char in password)
     special_chars = "!@#$%^&*(),.?\":{}|<>"
     has_special = any(char in special_chars for char in password)
     if not (is_long_enough and has_number and has_letter and has_special):
            return False
     return True


def nameCheack(name:str)->bool:
    has_number=any(char.isdigit()for char in name)
    special_chars = "!@#$%^&*(),.?\":{}|<>"
    has_special = any(char in special_chars for char in name)

    if has_number or has_special:
         return False
    return True