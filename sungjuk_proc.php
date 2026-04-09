<?php
declare(strict_types=1);

require_once __DIR__ . '/db.php';

ensure_sungjuk_table($mysqli);

function post_string(string $key): string
{
    return isset($_POST[$key]) ? trim((string)$_POST[$key]) : '';
}

function post_int(string $key): int
{
    return isset($_POST[$key]) ? (int)$_POST[$key] : -1;
}

function validate_score(string $label, int $score): void
{
    if ($score < 0 || $score > 100) {
        exit($label . ' 점수는 0~100 사이여야 합니다.');
    }
}

function calculate_grade(float $average): string
{
    if ($average >= 90.0) {
        return 'A';
    }
    if ($average >= 80.0) {
        return 'B';
    }
    if ($average >= 70.0) {
        return 'C';
    }
    if ($average >= 60.0) {
        return 'D';
    }
    return 'F';
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    ?>
    <!doctype html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>sungjuk_proc.php</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 24px; }
            label { display: block; margin-top: 10px; }
            input { width: 220px; padding: 6px; margin-top: 4px; }
            button { margin-top: 12px; padding: 8px 14px; }
        </style>
    </head>
    <body>
        <h1>성적 입력</h1>
        <form method="post" action="sungjuk_proc.php">
            <label>학번
                <input type="text" name="hakbun" required>
            </label>
            <label>출석(0~100)
                <input type="number" name="attendance" min="0" max="100" required>
            </label>
            <label>과제(0~100)
                <input type="number" name="assignment" min="0" max="100" required>
            </label>
            <label>중간(0~100)
                <input type="number" name="midterm" min="0" max="100" required>
            </label>
            <label>기말(0~100)
                <input type="number" name="final" min="0" max="100" required>
            </label>
            <button type="submit">계산 후 저장</button>
        </form>
        <p><a href="sungjuk_list.php">저장된 전체 목록 보기</a></p>
    </body>
    </html>
    <?php
    exit;
}

$hakbun = post_string('hakbun');
$attendance = post_int('attendance');
$assignmentScore = post_int('assignment');
$midtermScore = post_int('midterm');
$finalScore = post_int('final');

if ($hakbun === '') {
    exit('학번을 입력하세요.');
}

validate_score('출석', $attendance);
validate_score('과제', $assignmentScore);
validate_score('중간', $midtermScore);
validate_score('기말', $finalScore);

$totalScore = $attendance + $assignmentScore + $midtermScore + $finalScore;
$averageScore = round($totalScore / 4, 2);
$grade = calculate_grade($averageScore);

$sql = 'INSERT INTO sungjuk (hakbun, attendance, assignment_score, midterm_score, final_score, total_score, average_score, grade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)';
$stmt = $mysqli->prepare($sql);

if (!$stmt) {
    http_response_code(500);
    exit('INSERT 준비 실패: ' . $mysqli->error);
}

$stmt->bind_param(
    'siiiiids',
    $hakbun,
    $attendance,
    $assignmentScore,
    $midtermScore,
    $finalScore,
    $totalScore,
    $averageScore,
    $grade
);

if (!$stmt->execute()) {
    http_response_code(500);
    exit('데이터 저장 실패: ' . $stmt->error);
}

$stmt->close();
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>성적 처리 결과</title>
</head>
<body>
    <h1>성적 처리 결과</h1>
    <ul>
        <li>학번: <?= htmlspecialchars($hakbun, ENT_QUOTES, 'UTF-8') ?></li>
        <li>출석: <?= $attendance ?></li>
        <li>과제: <?= $assignmentScore ?></li>
        <li>중간: <?= $midtermScore ?></li>
        <li>기말: <?= $finalScore ?></li>
        <li>합계: <?= $totalScore ?></li>
        <li>평균: <?= number_format($averageScore, 2) ?></li>
        <li>평점: <?= $grade ?></li>
    </ul>
    <p>
        <a href="sungjuk_list.php">저장된 전체 목록 보기</a>
    </p>
</body>
</html>
