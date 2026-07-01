import random
from apps.employees.models import Employee

def generate_employee_code(first_name: str, last_name: str) -> str:
    """
    Generate unique employee code.
    Format: First initial + Last initial + 3 random digits
    Example: Krish Patel -> KP029
    """

    first_initial = first_name[0].upper() if first_name else "X"
    last_initial  = last_name[0].upper()  if last_name  else "X"
    prefix = f"{first_initial}{last_initial}"

    max_attempts = 20
    for _ in range(max_attempts):
        digits = str(random.randint(0, 999)).zfill(3)  # 000 to 999
        code = f"{prefix}{digits}"                      # e.g. KP029
        if not Employee.objects.filter(employee_code=code).exists():
            return code

    # Fallback: use 4 digits if 3-digit space exhausted
    for _ in range(max_attempts):
        digits = str(random.randint(0, 9999)).zfill(4)
        code = f"{prefix}{digits}"
        if not Employee.objects.filter(employee_code=code).exists():
            return code

    raise ValueError(f"Could not generate unique employee code for prefix {prefix}")
