import 'dart:convert';
import 'package:http/http.dart' as http;

class Message {
  final String role;
  final String content;
  Message({required this.role, required this.content});
  factory Message.fromJson(Map<String, dynamic> j) =>
      Message(role: j['role'], content: j['content']);
}

class ChatService {
  ChatService({this.baseUrl = 'http://127.0.0.1:8000'});
  //ChatService({this.baseUrl = 'http://172.20.10.2:8000'});
  //ChatService({this.baseUrl = 'http://172.20.10.2:8000'});

  final String baseUrl;
  String? sessionId;

  /// Start a brand-new session, store its ID locally, and return it.
  Future<String> initSession() async {
    final res = await http.post(Uri.parse('$baseUrl/sessions'));
    if (res.statusCode != 200) {
      throw Exception('Failed to start session');
    }
    final sid = res.body.replaceAll('"', '');
    sessionId = sid;
    return sid;
  }

  /// List ALL session IDs on the server.
  Future<List<String>> listSessions() async {
    final res = await http.get(Uri.parse('$baseUrl/sessions'));
    if (res.statusCode != 200) {
      throw Exception('Failed to list sessions');
    }
    final List<dynamic> data = json.decode(res.body);
    return data.cast<String>();
  }

  /// Fetch history for an arbitrary session.
  Future<List<Message>> fetchMessagesForSession(String sid) async {
    final res = await http.get(Uri.parse('$baseUrl/sessions/$sid/messages'));
    if (res.statusCode != 200) {
      throw Exception('Failed to load messages for session $sid');
    }
    final List<dynamic> data = json.decode(res.body);
    return data.map((e) => Message.fromJson(e)).toList();
  }

  /// Fetch for *current* sessionId.
  Future<List<Message>> fetchMessages() {
    if (sessionId == null) throw Exception('Session not initialized');
    return fetchMessagesForSession(sessionId!);
  }

  /// Send one user message to current session.
  Future<Message> sendMessage(String text) async {
    if (sessionId == null) throw Exception('Session not initialized');
    final res = await http.post(
      Uri.parse('$baseUrl/sessions/$sessionId/messages'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'content': text}),
    );
    if (res.statusCode != 200) {
      throw Exception('Failed to send message');
    }
    return Message.fromJson(json.decode(res.body));
  }
}
