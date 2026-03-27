def calculate_grade(average):
    if average >= 90:
        return "A"
    if average >= 80:
        return "B"
    if average >= 70:
        return "C"
    if average >= 60:
        return "D"
    return "F"


def main():
    name = input("이름을 입력하세요: ")
    grade_level = input("학년을 입력하세요: ")
    english = float(input("영어 점수를 입력하세요: "))
    korean = float(input("국어 점수를 입력하세요: "))
    math = float(input("수학 점수를 입력하세요: "))

    average = (english + korean + math) / 3
    letter_grade = calculate_grade(average)

    print("\n[성적 결과]")
    print(f"이름: {name}")
    print(f"학년: {grade_level}")
    print(f"평균점수: {average:.2f}")
    print(f"학점: {letter_grade}")


if __name__ == "__main__":
    main()
