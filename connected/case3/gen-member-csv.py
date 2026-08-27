import csv
import random
import string


def rand_digits(n):
    return "".join(random.choice(string.digits) for _ in range(n))


def rand_name():
    first = random.choice([
        "민준", "서준", "도윤", "예준", "시우",
        "하준", "지호", "현우", "준혁", "건우",
        "서연", "서윤", "지우", "하은", "민서",
        "예은", "유진", "수빈", "채원", "다은",
        "지훈", "정우", "성민", "승현", "태윤",
        "은지", "수민", "유나", "하나", "소연",
        "지민", "유정", "가은", "현지", "지원",
        "동현", "재훈", "민재", "주원", "연우"

    ])
    last = random.choice([
        "김", "이", "박", "최", "정",
        "강", "조", "윤", "장", "임",
        "한", "오", "서", "신", "권",
        "황", "안", "송", "류", "전"
    ])
    return last + first


def rand_email(name):
    return f"user{random.randint(1000,9999)}@cloudneta.com"


def rand_phone():
    return f"010-{rand_digits(4)}-{rand_digits(4)}"


def rand_rrn():
    yy = random.randint(70, 99)
    mm = random.randint(1, 12)
    dd = random.randint(1, 28)
    gender = random.choice(["1", "2"])

    return f"{yy:02d}{mm:02d}{dd:02d}-{gender}{rand_digits(6)}"


def gen_rows(count):
    rows = []

    grades = ["VIP", "GOLD", "SILVER"]

    for i in range(1, count + 1):
        rows.append({
            "customer_id": f"CUST-{i:04d}",
            "name": rand_name(),
            "email": rand_email(""),
            "phone": rand_phone(),
            "rrn": rand_rrn(),
            "grade": random.choice(grades),
            "point": random.randint(1000, 200000)
        })

    return rows


def write_csv(filename, rows):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys())
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = gen_rows(10)

    write_csv(
        "membership-data.csv",
        rows
    )

    print("generated: membership-data.csv")


if __name__ == "__main__":
    main()
