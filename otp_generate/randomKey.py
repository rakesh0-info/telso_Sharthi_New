import random
import string


def get_random_letters():
    # Combine lowercase and uppercase letters
    letters = string.ascii_letters
    # Pick 10 random letters and join them into a string
    random_10 = "".join(random.choices(letters, k=10))
    return {"random_letters": random_10}

def get_random_pass(length=12):

   if length < 4:
        raise ValueError("Password length must be at least 4 to include all character types.")
    
    # Define character pools
   lower = string.ascii_lowercase
   upper = string.ascii_uppercase
   digits = string.digits
   special = "#$*!@%"  # You can customize your specific special characters here
    
    # Ensure at least one of each required type is present
   password_chars = [
        random.choice(lower),
        random.choice(upper),
        random.choice(digits),
        random.choice(special)
    ]
    
    # Fill the remaining length from all combined pools
   all_chars = lower + upper + digits + special
   password_chars += [random.choice(all_chars) for _ in range(length - 4)]
    
    # Shuffle to make it completely random
   random.shuffle(password_chars)
    
   return ''.join(password_chars)





