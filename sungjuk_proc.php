<?php
$db_con = mysqli_connect("localhost", "test", "test1234", "testdb");
if (!$db_con) {
    exit("DB 연결 실패");
}

$create_sql = "CREATE TABLE IF NOT EXISTS sungjuk (
id INT AUTO_INCREMENT PRIMARY KEY,
hakbun VARCHAR(20) NOT NULL,
attendance INT NOT NULL,
assignment_score INT NOT NULL,
midterm_score INT NOT NULL,
final_score INT NOT NULL,
total_score INT NOT NULL,
average_score DOUBLE(5,2) NOT NULL,
grade VARCHAR(2) NOT NULL,
created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)";
mysqli_query($db_con, $create_sql);

if (!isset($_POST["hakbun"])) {
?>
<h2>성적 입력하고 계산 + 저장하기</h2><hr>
<form method="post" action="sungjuk_proc.php">
학번 : <input type="text" name="hakbun" size="20"><br><br>
출석 : <input type="number" name="attendance" min="0" max="100"><br><br>
과제 : <input type="number" name="assignment" min="0" max="100"><br><br>
중간 : <input type="number" name="midterm" min="0" max="100"><br><br>
기말 : <input type="number" name="final" min="0" max="100"><br><br>
<input type="submit" value="계산 후 저장">
</form>
<p><a href="sungjuk_list.php">sungjuk 목록 보기</a></p>
<?php
    mysqli_close($db_con);
    exit;
}

$hakbun = $_POST["hakbun"];
$attendance = (int)$_POST["attendance"];
$assignment = (int)$_POST["assignment"];
$midterm = (int)$_POST["midterm"];
$final = (int)$_POST["final"];

$total = $attendance + $assignment + $midterm + $final;
$avg = $total / 4;

if ($avg >= 90) $grade = "A";
else if ($avg >= 80) $grade = "B";
else if ($avg >= 70) $grade = "C";
else if ($avg >= 60) $grade = "D";
else $grade = "F";

$sql = "INSERT INTO sungjuk (hakbun, attendance, assignment_score, midterm_score, final_score, total_score, average_score, grade)
VALUES ('$hakbun', $attendance, $assignment, $midterm, $final, $total, $avg, '$grade')";
$result = mysqli_query($db_con, $sql);
?>
<h2>입력한 성적 계산 결과</h2><hr>
<?php
echo "<p>학번 : " . $hakbun;
echo "<p>출석 : " . $attendance;
echo "<p>과제 : " . $assignment;
echo "<p>중간 : " . $midterm;
echo "<p>기말 : " . $final;
echo "<p>합계 : " . $total;
echo "<p>평균 : " . round($avg, 2);
echo "<p>평점 : " . $grade;
echo "<hr>";

if ($result) echo "<p>saving procedure is ok";
else echo "<p>saving procedure is fail";
?>
<p><a href="sungjuk_proc.php">다시 입력하기</a></p>
<p><a href="sungjuk_list.php">sungjuk 목록 보기</a></p>
<?php mysqli_close($db_con); ?>
