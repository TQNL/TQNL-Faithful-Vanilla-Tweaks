package local.copperpack;

import java.io.InputStream;
import java.io.Reader;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.zip.ZipFile;
import java.util.List;
import java.util.stream.Stream;

/** Probe the game's own ZIP reader, metadata parser and overlay resolver.
 * Reflection plus official mappings also supports the obfuscated 1.21.x clients.
 * No Minecraft window, profile, world or rendering runtime is started.
 */
public final class NativePackCheck {
    private static final Properties names = new Properties();

    private static Class<?> type(String alias) throws Exception {
        return Class.forName(names.getProperty(alias + ".class"));
    }

    private static Method method(String alias, String name, Class<?>... arguments) throws Exception {
        Class<?> owner = type(alias);
        String candidates = names.getProperty(alias + ".method." + name, name);
        for (String candidate : candidates.split(",")) {
            try { return owner.getMethod(candidate, arguments); }
            catch (NoSuchMethodException ignored) { }
        }
        throw new NoSuchMethodException(alias + "." + name);
    }

    private static Object field(String alias, String name) throws Exception {
        return type(alias).getField(names.getProperty(alias + ".field." + name, name)).get(null);
    }

    private static String sha(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    public static void main(String[] args) throws Exception {
        java.io.PrintStream errors = System.err;
        try { run(args); }
        catch (Throwable error) {
            error.printStackTrace(errors);
            System.exit(1);
        }
    }

    private static void run(String[] args) throws Exception {
        java.io.PrintStream report = System.out;
        try (Reader reader = Files.newBufferedReader(Path.of(args[0]), StandardCharsets.UTF_8)) {
            names.load(reader);
        }
        method("SharedConstants", "tryDetectVersion").invoke(null);
        method("Bootstrap", "bootStrap").invoke(null);
        Object title = method("Component", "literal", String.class).invoke(null, "Universal pack check");
        Object location = type("Location").getConstructor(String.class, type("Component"),
                type("Source"), Optional.class).newInstance("universal-check", title,
                field("Source", "DEFAULT"), Optional.empty());
        Object supplier = type("FileSupplier").getConstructor(java.io.File.class)
                .newInstance(Path.of(args[1]).toFile());
        Object packType = field("PackType", "CLIENT_RESOURCES");
        Object format = type("Format").getConstructor(int.class, int.class)
                .newInstance(Integer.parseInt(args[2]), Integer.parseInt(args[3]));
        Object metadata = method("Pack", "readPackMetadata", type("Location"),
                type("Supplier"), type("Format"), type("PackType"))
                .invoke(null, location, supplier, format, packType);
        if (metadata == null) throw new IllegalStateException("Minecraft rejected pack metadata");
        Object compatibility = method("Metadata", "compatibility").invoke(metadata);
        Object overlays = method("Metadata", "overlays").invoke(metadata);
        report.println("NATIVE_COMPATIBILITY=" + compatibility);
        report.println("NATIVE_OVERLAYS=" + overlays);
        Map<String, byte[]> resources = new TreeMap<>();
        List<?> packs;
        try {
            Object full = method("FileSupplier", "openFull", type("Location"), type("Metadata"))
                    .invoke(supplier, location, metadata);
            packs = List.of(full);
        } catch (NoSuchMethodException newerApi) {
            try (Stream<?> stream = (Stream<?>) method("FileSupplier", "openResources",
                    type("Location"), type("Metadata")).invoke(supplier, location, metadata)) {
                packs = stream.toList();
            }
        }
        Object manager = type("Manager").getConstructor(type("PackType"), List.class)
                .newInstance(packType, packs);
        Set<String> identifiers = new TreeSet<>();
        try (ZipFile archive = new ZipFile(args[1])) {
            archive.stream().forEach(entry -> {
                if (entry.isDirectory()) return;
                String name = entry.getName();
                int start = name.startsWith("assets/") ? 0 : name.indexOf("/assets/") + 1;
                if (start < 1 && !name.startsWith("assets/")) return;
                String[] parts = name.substring(start).split("/", 3);
                if (parts.length == 3) identifiers.add(parts[1] + ":" + parts[2]);
            });
        }
        try (AutoCloseable ignored = (AutoCloseable) manager) {
            for (String name : identifiers) {
                Object id = method("Identifier", "parse", String.class).invoke(null, name);
                Optional<?> resource = (Optional<?>) method("Manager", "getResource", type("Identifier"))
                        .invoke(manager, id);
                if (resource.isEmpty()) continue; // The 26.x-only texture is absent on 1.21.x.
                try (InputStream stream = (InputStream) method("Resource", "open").invoke(resource.get())) {
                    String[] parts = name.split(":", 2);
                    resources.put("assets/" + parts[0] + "/" + parts[1], stream.readAllBytes());
                }
            }
        }
        StringBuilder records = new StringBuilder();
        for (Map.Entry<String, byte[]> entry : resources.entrySet()) {
            records.append(sha(entry.getValue())).append("  ").append(entry.getKey()).append('\n');
        }
        report.println("NATIVE_ASSET_COUNT=" + resources.size());
        report.println("NATIVE_ASSET_HASH=" + sha(records.toString().getBytes(StandardCharsets.UTF_8)));
    }
}
