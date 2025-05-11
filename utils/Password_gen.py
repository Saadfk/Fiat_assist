import hashlib
from math import gcd

# Function to generate MD5 hash
def generate_md5(x, y):
    # Concatenate the two inputs and encode as bytes
    concatenated = f"{x}{y}".encode('utf-8')
    # Generate MD5 hash
    md5_hash = hashlib.md5(concatenated).hexdigest()
    return md5_hash

# Function to calculate Least Common Multiple (LCM)
def calculate_lcm(a, b):
    # Calculate the Greatest Common Divisor (GCD)
    greatest_common_divisor = gcd(a, b)
    # Calculate Least Common Multiple (LCM) using the formula
    lcm = abs(a * b) // greatest_common_divisor
    return lcm

# Function to generate the required string
def generate_combined_output(x, y, a, b):
    md5_hash = generate_md5(x, y)
    lcm = calculate_lcm(a, b)
    # Extract the first 4 characters of the MD5 hash
    md5_part = md5_hash[:4]
    # Extract the firsSaadt 4 digits of the LCM
    lcm_part = str(lcm)[:4]
    # Combine the parts with "!"
    result = f"{md5_part}!{lcm_part}"
    return result

# Main program
if __name__ == "__main__":
    # Get inputs from the user
    x = input("Enter the first string (x): ")
    y = input("Enter the second string (y): ")
    a = int(input("Enter the first integer (a): "))
    b = int(input("Enter the second integer (b): "))

    # Generate and display the output
    output = generate_combined_output(x, y, a, b)
    print("Generated Output:", output)
