// Compile once to .runtime/site-keychain. Secrets travel only through stdin/stdout pipes.
import Foundation
import Security
import LocalAuthentication

func fail(_ code: OSStatus) -> Never {
    FileHandle.standardError.write(Data("keychain error \(code)\n".utf8)); exit(1)
}
guard CommandLine.arguments.count == 3 else { fail(errSecParam) }
let action = CommandLine.arguments[1], account = CommandLine.arguments[2]
guard ["get", "set", "delete"].contains(action),
      let url = URL(string: account), url.scheme == "https", url.host != nil,
      url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
      url.path.isEmpty else { fail(errSecParam) }
let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: "com.chatschedulehub.site-access",
    kSecAttrAccount as String: account]
if action == "set" {
    guard let line = readLine(), !line.isEmpty, line.utf8.count < 16384 else { fail(errSecParam) }
    let value = Data(line.utf8)
    var attributes = query; attributes[kSecValueData as String] = value
    var code = SecItemAdd(attributes as CFDictionary, nil)
    if code == errSecDuplicateItem {
        code = SecItemUpdate(query as CFDictionary, [kSecValueData as String:value] as CFDictionary)
    }
    guard code == errSecSuccess else { fail(code) }
} else if action == "delete" {
    let code = SecItemDelete(query as CFDictionary)
    guard code == errSecSuccess || code == errSecItemNotFound else { fail(code) }
} else {
    var lookup = query
    lookup[kSecReturnData as String] = true
    lookup[kSecMatchLimit as String] = kSecMatchLimitOne
    // Background runs fail closed instead of waiting on a password prompt.
    let context = LAContext(); context.interactionNotAllowed = true
    lookup[kSecUseAuthenticationContext as String] = context
    var result: CFTypeRef?
    let code = SecItemCopyMatching(lookup as CFDictionary, &result)
    guard code == errSecSuccess, let data = result as? Data else { fail(code) }
    FileHandle.standardOutput.write(data)
}
