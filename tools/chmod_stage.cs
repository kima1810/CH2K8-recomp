using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;

public static class ChmodStage
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateHardLink(string destination, string source, IntPtr reserved);

    public static void CopyTree(string source, string destination, bool linkAssets)
    {
        var pending = new Stack<string>();
        pending.Push(source);
        bool runtime = !linkAssets && Path.GetFileName(source) == "_runtime";
        int entries = 0;
        while (pending.Count != 0)
        {
            var directory = pending.Pop();
            var relative = directory.Substring(source.Length).TrimStart(Path.DirectorySeparatorChar);
            var output = Path.Combine(destination, relative);
            Directory.CreateDirectory(output);

            foreach (var entry in Directory.EnumerateFileSystemEntries(directory))
            {
                if (++entries > 1000000)
                    throw new IOException("Too many files or directories in the game tree.");
                var attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Game tree contains a symlink or junction: " + entry);
                if ((attributes & FileAttributes.Directory) != 0)
                {
                    // Native prepare regenerates these outputs from the staged assets.
                    var directoryName = Path.GetFileName(entry);
                    if (runtime && directory == source &&
                        (directoryName == "headers" || directoryName == "padding" ||
                         directoryName == "scene-textures"))
                        continue;
                    pending.Push(entry);
                    continue;
                }

                var name = Path.GetFileName(entry);
                var target = Path.Combine(output, name);
                // Native prepare can write metadata and generated paired files.
                // Existing payloads are read, and the launcher unlinks every
                // replaced asset before copying its mod payload.
                bool immutable = name.Equals("payload.dat", StringComparison.Ordinal)
                    || name.Equals("scene.dat", StringComparison.Ordinal)
                    || name.Equals("scene_gpu.dat", StringComparison.Ordinal)
                    || name.Equals("texture_header.dat", StringComparison.Ordinal)
                    || name.Equals("texture_pixels.dat", StringComparison.Ordinal)
                    || (name.StartsWith("block", StringComparison.Ordinal)
                        && (name.EndsWith(".dat", StringComparison.Ordinal)
                            || name.EndsWith(".stored", StringComparison.Ordinal)));
                bool pairedOutput = Array.IndexOf(relative.Split(Path.DirectorySeparatorChar), "_loose") >= 0;
                if (!linkAssets || !immutable || pairedOutput || !CreateHardLink(target, entry, IntPtr.Zero))
                    File.Copy(entry, target);
            }
        }
    }
}
