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
        body { font-family: Arial, sans-serif; margin: 24px; }
        table { border-collapse: collapse; width: 100%; margin-top: 16px; }
        th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
        th { background-color: #f5f5f5; }
        .small { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <h1>성적 목록 (sungjuk 테이블)</h1>
    <p class="small">총 <?= (int)$result->num_rows ?>건</p>

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
                <td colspan="10">저장된 데이터가 없습니다.</td>
            </tr>
        <?php else: ?>
            <?php while ($row = $result->fetch_assoc()): ?>
                <tr>
                    <td><?= (int)$row['id'] ?></td>
                    <td><?= htmlspecialchars((string)$row['hakbun'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                    <td><?= (int)$row['attendance'] ?></td>
                    <td><?= (int)$row['assignment_score'] ?></td>
                    <td><?= (int)$row['midterm_score'] ?></td>
                    <td><?= (int)$row['final_score'] ?></td>
                    <td><?= (int)$row['total_score'] ?></td>
                    <td><?= number_format((float)$row['average_score'], 2) ?></td>
                    <td><?= htmlspecialchars((string)$row['grade'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                    <td><?= htmlspecialchars((string)$row['created_at'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                </tr>
            <?php endwhile; ?>
        <?php endif; ?>
        </tbody>
    </table>

    <p><a href="sungjuk_proc.php">sungjuk_proc.php로 이동</a></p>
</body>
</html>
