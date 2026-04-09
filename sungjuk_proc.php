<?php
declare(strict_types=1);

require_once __DIR__ . '/db.php';

ensure_sungjuk_table($mysqli);

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function post_string(string $key): string
{
    return trim((string)($_POST[$key] ?? ''));
}

function post_int(string $key): int
{
    return (int)($_POST[$key] ?? -1);
}

function calc_grade(float $avg): string
{
    if ($avg >= 90.0) {
        return 'A';
    }
    if ($avg >= 80.0) {
        return 'B';
    }
    if ($avg >= 70.0) {
        return 'C';
    }
    if ($avg >= 60.0) {
        return 'D';
    }
    return 'F';
}

function validate_score(string $label, int $score): void
{
    if ($score < 0 || $score > 100) {
        exit($label . ' 점수는 0~100 범위만 입력 가능합니다.');
    }
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    ?>
    <!doctype html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>성적 입력하기</title>
        <style>
            :root {
                --bg: #f4f7ff;
                --card: #ffffff;
                --primary: #4f46e5;
                --primary-dark: #4338ca;
                --text: #0f172a;
                --muted: #64748b;
                --border: #dbe3f0;
                --shadow: 0 14px 32px rgba(15, 23, 42, 0.10);
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                min-height: 100vh;
                background: linear-gradient(180deg, #e9edff 0%, var(--bg) 100%);
                font-family: "Noto Sans KR", Arial, sans-serif;
                color: var(--text);
                padding: 26px;
            }
            .wrap {
                max-width: 840px;
                margin: 0 auto;
            }
            .card {
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 18px;
                box-shadow: var(--shadow);
                padding: 28px;
            }
            h2 {
                margin: 0 0 8px;
                font-size: 28px;
            }
            .desc {
                margin: 0 0 22px;
                color: var(--muted);
            }
            .field {
                margin-bottom: 14px;
            }
            label {
                display: block;
                margin-bottom: 7px;
                font-weight: 700;
            }
            input {
                width: 100%;
                border: 1px solid #ccd5e3;
                border-radius: 12px;
                padding: 11px 12px;
                font-size: 15px;
                outline: none;
            }
            input:focus {
                border-color: var(--primary);
                box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.14);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
            }
            .actions {
                margin-top: 18px;
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }
            button, a.btn {
                border: 0;
                border-radius: 12px;
                padding: 11px 15px;
                text-decoration: none;
                font-size: 15px;
                font-weight: 700;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            button {
                background: var(--primary);
                color: #fff;
                cursor: pointer;
            }
            button:hover { background: var(--primary-dark); }
            a.btn {
                background: #eef2ff;
                color: #3730a3;
                border: 1px solid #d9ddff;
            }
        </style>
    </head>
    <body>
    <div class="wrap">
        <div class="card">
            <h2>성적 처리 프로그램 (sungjuk_proc.php)</h2>
            <p class="desc">학번, 출석, 과제, 중간, 기말 점수를 입력하면 합계/평점을 계산하고 sungjuk 테이블에 저장합니다.</p>
            <form method="post" action="sungjuk_proc.php">
                <div class="field">
                    <label for="hakbun">학번</label>
                    <input id="hakbun" type="text" name="hakbun" maxlength="20" required placeholder="예: 20260001">
                </div>
                <div class="grid">
                    <div class="field">
                        <label for="attendance">출석 (0~100)</label>
                        <input id="attendance" type="number" name="attendance" min="0" max="100" required>
                    </div>
                    <div class="field">
                        <label for="assignment">과제 (0~100)</label>
                        <input id="assignment" type="number" name="assignment" min="0" max="100" required>
                    </div>
                    <div class="field">
                        <label for="midterm">중간 (0~100)</label>
                        <input id="midterm" type="number" name="midterm" min="0" max="100" required>
                    </div>
                    <div class="field">
                        <label for="final">기말 (0~100)</label>
                        <input id="final" type="number" name="final" min="0" max="100" required>
                    </div>
                </div>
                <div class="actions">
                    <button type="submit">계산 후 저장</button>
                    <a class="btn" href="sungjuk_list.php">성적 목록 보기</a>
                </div>
            </form>
        </div>
    </div>
    </body>
    </html>
    <?php
    exit;
}

$hakbun = post_string('hakbun');
$attendance = post_int('attendance');
$assignment = post_int('assignment');
$midterm = post_int('midterm');
$final = post_int('final');

if ($hakbun === '') {
    exit('학번을 입력하세요.');
}

validate_score('출석', $attendance);
validate_score('과제', $assignment);
validate_score('중간', $midterm);
validate_score('기말', $final);

$total = $attendance + $assignment + $midterm + $final;
$average = round($total / 4, 2);
$grade = calc_grade($average);

$sql = 'INSERT INTO sungjuk (hakbun, attendance, assignment_score, midterm_score, final_score, total_score, average_score, grade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)';
$stmt = $mysqli->prepare($sql);
if (!$stmt) {
    http_response_code(500);
    exit('SQL 준비 실패: ' . h($mysqli->error));
}

$stmt->bind_param('siiiiids', $hakbun, $attendance, $assignment, $midterm, $final, $total, $average, $grade);
$ok = $stmt->execute();
$affectedRows = $stmt->affected_rows;
$stmt->close();
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>성적 처리 결과</title>
    <style>
        :root {
            --bg: #0f172a;
            --card: #18243f;
            --text: #e2e8f0;
            --muted: #94a3b8;
            --ok: #34d399;
            --fail: #fb7185;
            --accent: #60a5fa;
            --border: #334155;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            background: radial-gradient(circle at 20% 5%, #1d4ed8 0%, var(--bg) 55%);
            color: var(--text);
            font-family: "Noto Sans KR", Arial, sans-serif;
            padding: 24px;
        }
        .card {
            width: min(780px, 100%);
            border-radius: 18px;
            border: 1px solid var(--border);
            background: linear-gradient(180deg, rgba(255,255,255,0.03), transparent), var(--card);
            box-shadow: 0 22px 52px rgba(0, 0, 0, 0.35);
            padding: 24px;
        }
        h2 {
            margin: 0 0 8px;
            font-size: 28px;
        }
        hr {
            border: 0;
            border-top: 1px solid var(--border);
            margin: 10px 0 18px;
        }
        .grid {
            display: grid;
            grid-template-columns: 130px 1fr;
            gap: 10px 12px;
        }
        .k { color: var(--muted); }
        .v { font-weight: 700; }
        .status {
            margin-top: 18px;
            font-size: 18px;
            font-weight: 700;
        }
        .ok { color: var(--ok); }
        .fail { color: var(--fail); }
        .actions {
            margin-top: 16px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        a.btn {
            text-decoration: none;
            color: #fff;
            background: var(--accent);
            border-radius: 10px;
            padding: 10px 14px;
            font-weight: 700;
        }
        a.btn.secondary {
            background: #475569;
        }
    </style>
</head>
<body>
    <section class="card">
        <h2>입력한 성적 계산 및 저장 결과</h2>
        <hr>
        <div class="grid">
            <div class="k">학번</div><div class="v"><?= h($hakbun) ?></div>
            <div class="k">출석</div><div class="v"><?= $attendance ?></div>
            <div class="k">과제</div><div class="v"><?= $assignment ?></div>
            <div class="k">중간</div><div class="v"><?= $midterm ?></div>
            <div class="k">기말</div><div class="v"><?= $final ?></div>
            <div class="k">합계</div><div class="v"><?= $total ?></div>
            <div class="k">평균</div><div class="v"><?= number_format($average, 2) ?></div>
            <div class="k">평점</div><div class="v"><?= h($grade) ?></div>
        </div>
        <?php if ($ok && $affectedRows > 0): ?>
            <p class="status ok">saving procedure is ok</p>
        <?php else: ?>
            <p class="status fail">saving procedure is fail</p>
        <?php endif; ?>
        <div class="actions">
            <a class="btn" href="sungjuk_list.php">목록 보기</a>
            <a class="btn secondary" href="sungjuk_proc.php">다시 입력</a>
        </div>
    </section>
</body>
</html>
