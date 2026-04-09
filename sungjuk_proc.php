<?php
declare(strict_types=1);
require_once __DIR__ . '/db.php';
ensure_sungjuk_table($mysqli);

$h = fn($v) => htmlspecialchars((string)$v, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$gradeOf = fn(float $a) => $a >= 90 ? 'A' : ($a >= 80 ? 'B' : ($a >= 70 ? 'C' : ($a >= 60 ? 'D' : 'F')));

if ($_SERVER['REQUEST_METHOD'] !== 'POST') { ?>
<!doctype html>
<html lang="ko">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>sungjuk_proc.php</title>
  <style>
    body{margin:0;font-family:Arial,sans-serif;background:#f5f7ff;padding:24px}
    .card{max-width:760px;margin:auto;background:#fff;border-radius:14px;padding:20px;box-shadow:0 10px 26px rgba(0,0,0,.08)}
    h2{margin:0 0 8px}.muted{color:#666;margin:0 0 16px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.full{grid-column:1/-1}
    label{font-weight:700;font-size:14px}input{width:100%;margin-top:6px;padding:10px;border:1px solid #d2d8e4;border-radius:10px}
    .actions{margin-top:14px;display:flex;gap:8px;flex-wrap:wrap}
    button,a{border:0;border-radius:10px;padding:10px 13px;font-weight:700;text-decoration:none}
    button{background:#2563eb;color:#fff}a{background:#eef2ff;color:#1e3a8a}
    @media(max-width:640px){.grid{grid-template-columns:1fr}}
  </style>
</head>
<body><section class="card">
  <h2>성적 처리 프로그램</h2>
  <p class="muted">학번/출석/과제/중간/기말 입력 → 합계/평점 계산 후 DB 저장</p>
  <form method="post" action="sungjuk_proc.php">
    <div class="grid">
      <div class="full"><label>학번<input name="hakbun" maxlength="20" required></label></div>
      <label>출석 (0~100)<input type="number" name="attendance" min="0" max="100" required></label>
      <label>과제 (0~100)<input type="number" name="assignment" min="0" max="100" required></label>
      <label>중간 (0~100)<input type="number" name="midterm" min="0" max="100" required></label>
      <label>기말 (0~100)<input type="number" name="final" min="0" max="100" required></label>
    </div>
    <div class="actions"><button>계산 후 저장</button><a href="sungjuk_list.php">성적 목록</a></div>
  </form>
</section></body></html>
<?php exit; }

$hakbun = trim((string)($_POST['hakbun'] ?? ''));
$attendance = (int)($_POST['attendance'] ?? -1);
$assignment = (int)($_POST['assignment'] ?? -1);
$midterm = (int)($_POST['midterm'] ?? -1);
$final = (int)($_POST['final'] ?? -1);
if ($hakbun === '') { exit('학번을 입력하세요.'); }
foreach (['출석' => $attendance, '과제' => $assignment, '중간' => $midterm, '기말' => $final] as $k => $v) {
    if ($v < 0 || $v > 100) { exit($k . ' 점수는 0~100만 입력 가능합니다.'); }
}

$total = $attendance + $assignment + $midterm + $final;
$average = round($total / 4, 2);
$grade = $gradeOf($average);

$stmt = $mysqli->prepare('INSERT INTO sungjuk (hakbun, attendance, assignment_score, midterm_score, final_score, total_score, average_score, grade) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
if (!$stmt) { exit('SQL 준비 실패'); }
$stmt->bind_param('siiiiids', $hakbun, $attendance, $assignment, $midterm, $final, $total, $average, $grade);
$ok = $stmt->execute() && $stmt->affected_rows > 0;
$stmt->close();
?>
<!doctype html>
<html lang="ko">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>성적 처리 결과</title>
  <style>
    body{margin:0;font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px}
    .card{max-width:760px;margin:auto;background:#1e293b;border-radius:14px;padding:20px}
    .row{display:grid;grid-template-columns:120px 1fr;gap:8px;padding:5px 0}.k{color:#94a3b8}.v{font-weight:700}
    .ok{color:#34d399}.fail{color:#fb7185}.actions{margin-top:14px;display:flex;gap:8px}
    a{background:#3b82f6;color:#fff;text-decoration:none;padding:9px 12px;border-radius:9px;font-weight:700}
    a.alt{background:#475569}
  </style>
</head>
<body><section class="card">
  <h2>성적 처리 결과</h2><hr>
  <div class="row"><div class="k">학번</div><div class="v"><?= $h($hakbun) ?></div></div>
  <div class="row"><div class="k">출석</div><div class="v"><?= $attendance ?></div></div>
  <div class="row"><div class="k">과제</div><div class="v"><?= $assignment ?></div></div>
  <div class="row"><div class="k">중간</div><div class="v"><?= $midterm ?></div></div>
  <div class="row"><div class="k">기말</div><div class="v"><?= $final ?></div></div>
  <div class="row"><div class="k">합계</div><div class="v"><?= $total ?></div></div>
  <div class="row"><div class="k">평균</div><div class="v"><?= number_format($average, 2) ?></div></div>
  <div class="row"><div class="k">평점</div><div class="v"><?= $h($grade) ?></div></div>
  <p class="<?= $ok ? 'ok' : 'fail' ?>"><?= $ok ? 'saving procedure is ok' : 'saving procedure is fail' ?></p>
  <div class="actions"><a href="sungjuk_list.php">목록 보기</a><a class="alt" href="sungjuk_proc.php">다시 입력</a></div>
</section></body></html>
