# Static PE32+ import reader. Reads bytes only; never loads binaries.
function Get-PeImports([string]$File) {
    $data = [IO.File]::ReadAllBytes($File)
    if ($data.Length -lt 64 -or $data[0] -ne 77 -or $data[1] -ne 90) { throw "Invalid Windows binary: $File" }
    $pe = [BitConverter]::ToInt32($data, 60)
    if ($pe -lt 0 -or $pe + 24 -gt $data.Length -or [BitConverter]::ToUInt32($data, $pe) -ne 0x4550) { throw 'Invalid PE signature' }
    if ([BitConverter]::ToUInt16($data, $pe + 4) -ne 0x8664) { throw 'Non-x64 beta binary' }
    $count = [BitConverter]::ToUInt16($data, $pe + 6)
    $size = [BitConverter]::ToUInt16($data, $pe + 20)
    if ($count -gt 128 -or $size -lt 240) { throw 'Unsupported PE section count/optional header size' }
    $optional = $pe + 24
    if ($optional + $size + $count * 40 -gt $data.Length -or [BitConverter]::ToUInt16($data, $optional) -ne 0x20b) { throw 'Invalid PE32+ headers' }
    $sections = @()
    for ($i=0; $i -lt $count; $i++) {
        $o = $optional + $size + $i * 40 + 8
        $sections += @{ virtual_size=[BitConverter]::ToUInt32($data,$o); address=[BitConverter]::ToUInt32($data,$o+4); raw_size=[BitConverter]::ToUInt32($data,$o+8); pointer=[BitConverter]::ToUInt32($data,$o+12) }
    }
    function Resolve-PeRva([uint32]$Value) {
        foreach ($s in $sections) {
            if ($Value -ge $s.address -and $Value -lt $s.address + [Math]::Max($s.virtual_size,$s.raw_size)) {
                $offset = [long]$s.pointer + $Value - $s.address
                if ($offset -lt 0 -or $offset -ge $data.Length) { throw 'Invalid PE RVA' }
                return [int]$offset
            }
        }
        throw 'Unmapped PE RVA'
    }
    foreach ($spec in @(@(1,20,12), @(13,32,4))) {
        $rva = [BitConverter]::ToUInt32($data,$optional+112+$spec[0]*8)
        if (-not $rva) { continue }
        $position = Resolve-PeRva $rva
        for ($n=0; $n -lt 10000; $n++) {
            if ($position + $spec[1] -gt $data.Length) { throw 'Truncated PE import table' }
            $nonzero = $false
            for ($i=0; $i -lt $spec[1]; $i++) { if ($data[$position+$i]) { $nonzero=$true; break } }
            if (-not $nonzero) { break }
            $start = Resolve-PeRva ([BitConverter]::ToUInt32($data,$position+$spec[2]))
            $end = $start
            while ($end -lt $data.Length -and $data[$end] -and $end-$start -lt 260) { $end++ }
            if ($end -eq $data.Length -or $data[$end]) { throw 'Unterminated/oversize PE import name' }
            [Text.Encoding]::ASCII.GetString($data,$start,$end-$start).ToLowerInvariant()
            $position += $spec[1]
        }
        if ($n -eq 10000) { throw 'Excessive PE import count' }
    }
}
