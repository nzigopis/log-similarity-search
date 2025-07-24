# Set the folder path where the files are located
$folderPath = "\\wsl.localhost\Ubuntu\home\nzigopis\repos\python\remote-diagnostics\logs.\Fluent~1610007591.1080"

# Get all the .zlf files in the folder
$files = Get-ChildItem -Path $folderPath -Filter "*.zlf"

# Loop through each file and extract its contents
foreach ($file in $files) {
    # Original .zlf file path
    $originalFilePath = $file.FullName

    # Rename file to have a .zip extension
    $newFilePath = [System.IO.Path]::ChangeExtension($originalFilePath, ".zip")
    try {
        Rename-Item -Path $originalFilePath -NewName (Split-Path $newFilePath -Leaf) -Force
        Write-Host "Renamed: $originalFilePath to $newFilePath"

        # Extract the .zip file to the same folder
        Expand-Archive -Path $newFilePath -DestinationPath $file.DirectoryName -Force
        Write-Host "Successfully extracted: $newFilePath"

    } catch {
        Write-Host "Failed to process file: $originalFilePath - $_"
    }
}