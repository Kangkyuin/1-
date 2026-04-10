<?php
declare(strict_types=1);
session_start();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: input.php');
    exit;
}

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

$tokenFromForm = (string)($_POST['csrf_token'] ?? '');
$tokenFromSession = (string)($_SESSION['sungjuk_csrf'] ?? '');
if ($tokenFromForm === '' || $tokenFromSession === '' || !hash_equals($tokenFromSession, $tokenFromForm)) {
    http_response_code(400);
    exit('잘못된 요청입니다. input.php에서 다시 시도하세요.');
}
unset($_SESSION['sungjuk_csrf']);

$studentId = trim((string)($_POST['student_id'] ?? ''));
$att = (int)($_POST['att'] ?? -1);
$hw = (int)($_POST['hw'] ?? -1);
$mid = (int)($_POST['mid'] ?? -1);
$final = (int)($_POST['final'] ?? -1);

if ($studentId === '') {
    exit('학번을 입력하세요.');
}

foreach (['출석' => $att, '과제' => $hw, '중간' => $mid, '기말' => $final] as $label => $score) {
    if ($score < 0 || $score > 100) {
        exit($label . ' 점수는 0~100 범위로 입력해야 합니다.');
    }
}

$total = $att + $hw + $mid + $final;
$avg = round($total / 4, 2);

if ($avg >= 90) {
    $grade = 'A';
} elseif ($avg >= 80) {
    $grade = 'B';
} elseif ($avg >= 70) {
    $grade = 'C';
} elseif ($avg >= 60) {
    $grade = 'D';
} else {
    $grade = 'F';
}

$mysqli = new mysqli('localhost', 'test', 'test1234', 'school');
if ($mysqli->connect_errno) {
    http_response_code(500);
    exit('DB 연결 실패: ' . h($mysqli->connect_error));
}
$mysqli->set_charset('utf8mb4');

$createSql = <<<SQL
CREATE TABLE IF NOT EXISTS sungjuk (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    att INT NOT NULL,
    hw INT NOT NULL,
    mid INT NOT NULL,
    final INT NOT NULL,
    total INT NOT NULL,
    average_score DECIMAL(5,2) NOT NULL,
    grade VARCHAR(2) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
SQL;

if (!$mysqli->query($createSql)) {
    http_response_code(500);
    exit('테이블 준비 실패: ' . h($mysqli->error));
}

$sql = 'INSERT INTO sungjuk (student_id, att, hw, mid, final, total, average_score, grade) VALUES (?, ?, ?, ?, ?, ?, ?, ?)';
$stmt = $mysqli->prepare($sql);
if (!$stmt) {
    http_response_code(500);
    exit('SQL 준비 실패: ' . h($mysqli->error));
}

$stmt->bind_param('siiiiids', $studentId, $att, $hw, $mid, $final, $total, $avg, $grade);
$ok = $stmt->execute() && $stmt->affected_rows > 0;
$stmt->close();
$mysqli->close();
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>성적 저장 결과</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Inter", "Noto Sans KR", Arial, sans-serif;
            color: #e2e8f0;
            background:
                radial-gradient(circle at 15% 10%, #1e3a8a 0%, transparent 30%),
                radial-gradient(circle at 85% 10%, #065f46 0%, transparent 32%),
                linear-gradient(165deg, #0b1228, #111827);
            display: grid;
            place-items: center;
            padding: 24px;
        }
        .card {
            width: min(780px, 100%);
            border-radius: 20px;
            border: 1px solid rgba(148, 163, 184, .28);
            background: rgba(15, 23, 42, .82);
            backdrop-filter: blur(10px);
            box-shadow: 0 30px 70px rgba(0,0,0,.40);
            padding: 24px;
        }
        h2 { margin: 0 0 10px; font-size: 28px; }
        .meta { color: #93c5fd; margin-bottom: 16px; }
        .grid {
            display: grid;
            grid-template-columns: 120px 1fr;
            gap: 10px 14px;
        }
        .k { color: #94a3b8; }
        .v { font-weight: 700; }
        .status {
            margin-top: 18px;
            padding: 12px;
            border-radius: 12px;
            font-weight: 700;
            border: 1px solid;
        }
        .ok { color: #86efac; background: rgba(22, 101, 52, .35); border-color: rgba(134, 239, 172, .4); }
        .fail { color: #fecdd3; background: rgba(159, 18, 57, .35); border-color: rgba(251, 113, 133, .45); }
        .actions {
            display: flex;
            gap: 10px;
            margin-top: 16px;
            flex-wrap: wrap;
        }
        a {
            text-decoration: none;
            color: #fff;
            font-weight: 700;
            padding: 10px 14px;
            border-radius: 10px;
            background: #2563eb;
        }
        a.alt { background: #334155; }
    </style>
</head>
<body>
<section class="card">
    <h2>성적 저장 완료</h2>
    <div class="meta">입력값 계산 및 DB 저장 결과</div>
    <div class="grid">
        <div class="k">학번</div><div class="v"><?= h($studentId) ?></div>
        <div class="k">출석</div><div class="v"><?= $att ?></div>
        <div class="k">과제</div><div class="v"><?= $hw ?></div>
        <div class="k">중간</div><div class="v"><?= $mid ?></div>
        <div class="k">기말</div><div class="v"><?= $final ?></div>
        <div class="k">합계</div><div class="v"><?= $total ?></div>
        <div class="k">평균</div><div class="v"><?= number_format($avg, 2) ?></div>
        <div class="k">평점</div><div class="v"><?= h($grade) ?></div>
    </div>

    <div class="status <?= $ok ? 'ok' : 'fail' ?>">
        <?= $ok ? '성적 저장 성공 (OK)' : '성적 저장 실패 (Fail)' ?>
    </div>

    <div class="actions">
        <a href="sungjuk_list_new.php">성적 리스트 보기</a>
        <a class="alt" href="input.php">다시 입력</a>
    </div>
</section>
</body>
</html>
