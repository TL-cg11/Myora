# 엄격한 JSON 파서: 중복 키 및 JSON 표준 밖의 숫자를 거절한다.
import json


# 중복 키가 마지막 값으로 덮이는 것을 막고 NaN·Infinity를 허용하지 않는다.
def loads(text: str):
    # JSON 객체의 키를 순서대로 확인하며 같은 키가 두 번 나오면 거절한다.
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_KEY")
            result[key] = value
        return result

    # JSON 표준에서 허용하지 않는 NaN·Infinity 토큰을 거절한다.
    def constant(_):
        raise ValueError("INVALID_NUMBER")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
