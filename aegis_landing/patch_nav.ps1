$files = Get-ChildItem "c:\Users\sudu\Desktop\kackp\aegis_landing\*.html"
foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8
    if ($content -notmatch 'nav\.js') {
        $content = $content -replace '</body>', '<script src="nav.js"></script>`n</body>'
        Set-Content $f.FullName $content -Encoding UTF8
        Write-Host "Patched: $($f.Name)"
    } else {
        Write-Host "Already has nav.js: $($f.Name)"
    }
}
