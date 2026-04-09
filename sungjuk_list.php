<?php
declare(strict_types=1);

require_once __DIR__ . '/db.php';

ensure_sungjuk_table($mysqli);

$sql = <<<SQL
SELECT
    id,
    hakbun,
    attendance,
    assignment_score,
    midterm_score,
    final_score,
    total_score,
    average_score,
    grade,
    created_at
FROM sungjuk
ORDER BY id DESC
SQL;

$result = $mysqli->query($sql);
if (!$result) {
    http_response_code(500);
    exit('목록 조회 실패: ' . $mysqli->error);
}
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>sungjuk_list.php</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Pretendard", "Noto Sans KR", Arial, sans-serif;
            background: linear-gradient(150deg, #eef2ff 0%, #f8fafc 38%, #e0f2fe 100%);
            color: #0f172a;
            padding: 30px 16px 60px;
        }
        .wrap {
            max-width: 1180px;
            margin: 0 auto;
        }
        .card {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 24px;
            box-shadow: 0 24px 50px rgba(15, 23, 42, 0.10);
            backdrop-filter: blur(10px);
            overflow: hidden;
        }
        .top {
            padding: 28px 30px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }
        h2 {
            margin: 0;
            font-size: 28px;
        }
        .meta {
            margin-top: 6px;
            color: #475569;
            font-size: 14px;
        }
        .tools a {
            display: inline-block;
            text-decoration: none;
            color: #1d4ed8;
            background: #dbeafe;
            border: 1px solid #bfdbfe;
            border-radius: 12px;
            padding: 10px 14px;
            font-weight: 700;
            margin-left: 8px;
        }
        .table-wrap {
            overflow-x: auto;
            padding: 24px 22px 28px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 980px;
        }
        th, td {
            border-bottom: 1px solid #e2e8f0;
            padding: 13px 10px;
            text-align: center;
        }
        th {
            background: #f8fafc;
            color: #334155;
            font-size: 13px;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        tbody tr:hover {
            background: #f8fbff;
        }
        .num {
            font-weight: 700;
        }
        .grade {
            font-weight: 800;
            color: #0f766e;
        }
        .empty {
            text-align: center;
            color: #64748b;
            padding: 40px 10px;
        }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <div class="top">
                <div>
                    <h2>sungjuk 테이블 전체 목록</h2>
                    <p class="meta">총 <?= (int)$result->num_rows ?>건</p>
                </div>
                <div class="tools">
                    <a href="sungjuk_proc.php">+ 성적 입력</a>
                    <a href="db_test.php">DB 테스트</a>
                </div>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                        <th>ID</th>
                        <th>학번</th>
                        <th>출석</th>
                        <th>과제</th>
                        <th>중간</th>
                        <th>기말</th>
                        <th>합계</th>
                        <th>평균</th>
                        <th>평점</th>
                        <th>저장일시</th>
                    </tr>
                    </thead>
                    <tbody>
                    <?php if ($result->num_rows === 0): ?>
                        <tr>
                            <td class="empty" colspan="10">저장된 데이터가 없습니다.</td>
                        </tr>
                    <?php else: ?>
                        <?php while ($row = $result->fetch_assoc()): ?>
                            <tr>
                                <td class="num"><?= (int)$row['id'] ?></td>
                                <td><?= htmlspecialchars((string)$row['hakbun'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                                <td><?= (int)$row['attendance'] ?></td>
                                <td><?= (int)$row['assignment_score'] ?></td>
                                <td><?= (int)$row['midterm_score'] ?></td>
                                <td><?= (int)$row['final_score'] ?></td>
                                <td class="num"><?= (int)$row['total_score'] ?></td>
                                <td><?= number_format((float)$row['average_score'], 2) ?></td>
                                <td class="grade"><?= htmlspecialchars((string)$row['grade'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                                <td><?= htmlspecialchars((string)$row['created_at'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            </tr>
                        <?php endwhile; ?>
                    <?php endif; ?>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
