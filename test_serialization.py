from pydantic import BaseModel, TypeAdapter
from enum import Enum

class Degree(Enum):
    BACHELOR = "bachelor"

class Education(BaseModel):
    degree: Degree

projected = {
    "edu": Education(degree=Degree.BACHELOR),
    "name": "Anurag"
}

try:
    print(TypeAdapter(dict).dump_json(projected).decode('utf-8'))
except Exception as e:
    print(f"Error dict: {e}")

try:
    from pydantic import RootModel
    print(RootModel(projected).model_dump_json())
except Exception as e:
    print(f"Error RootModel: {e}")
