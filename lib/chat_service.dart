import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

class Message {
  final String role;
  final String content;
  Message({required this.role, required this.content});
  factory Message.fromJson(Map<String, dynamic> j) =>
      Message(role: j['role'], content: j['content']);
}

class ChatService {
  ChatService({this.baseUrl = 'https://113e-78-190-223-66.ngrok-free.app'});
  //ChatService({this.baseUrl = 'http://172.20.10.2:8000'});
  //ChatService({this.baseUrl = 'http://172.20.10.2:8000'});

  final String baseUrl;
  String? sessionId;

  /// Start a brand-new session, store its ID locally, and return it.
  Future<String> initSession() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) throw Exception('No user signed in');

    final res = await http.post(Uri.parse('$baseUrl/sessions/${user.uid}'));

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
    final decoded = utf8.decode(res.bodyBytes);
    final List<dynamic> data = json.decode(decoded);
    return data.cast<String>();
  }

  /// Fetch history for an arbitrary session.
  Future<List<Message>> fetchMessagesForSession(String sid) async {
    final res = await http.get(Uri.parse('$baseUrl/sessions/$sid/messages'));
    if (res.statusCode != 200) {
      throw Exception('Failed to load messages for session $sid');
    }
    final decoded = utf8.decode(res.bodyBytes);
    final List<dynamic> data = json.decode(decoded);
    return data.map((e) => Message.fromJson(e)).toList();
  }

  /// Fetch for *current* sessionId.
  Future<List<Message>> fetchMessages() {
    if (sessionId == null) throw Exception('Session not initialized');
    return fetchMessagesForSession(sessionId!);
  }

  /// Send one user message to current session.
  Future<Message> sendMessage(
    String userId,
    String sessionId,
    String userInput,
  ) async {
    print(
      "🌐 Sending message to: https://113e-78-190-223-66.ngrok-free.app/sessions/$userId/$sessionId/messages",
    );

    final response = await http.post(
     Uri.parse('https://113e-78-190-223-66.ngrok-free.app/sessions/$userId/$sessionId/messages'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'content': userInput}),
    );

    print("🔁 Status code: ${response.statusCode}");
    print("📥 Response body: ${response.body}");

    if (response.statusCode != 200) {
      throw Exception('Failed to get AI response: ${response.body}');
    }

    final decoded = utf8.decode(response.bodyBytes);
    final data = jsonDecode(decoded);
    final aiText = data['content'] ?? 'No reply';
    final aiReply = Message(role: 'ai', content: aiText);

    //await _saveMessageToFirebase('user', userInput);
    //await _saveMessageToFirebase('ai', aiText);

    return aiReply;
  }

  Future<void> _saveMessageToFirebase(String role, String content) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null || sessionId == null) return;

    final docRef = FirebaseFirestore.instance
        .collection('users')
        .doc(user.uid)
        .collection('sessions')
        .doc(sessionId);

    // Create session doc with title if not yet created
    final doc = await docRef.get();
    if (!doc.exists && role == 'user') {
      await docRef.set({
        'title': content,
        'created_at': FieldValue.serverTimestamp(),
      });
    }

    // Save message
    await docRef.collection('messages').add({
      'role': role,
      'content': content,
      'timestamp': FieldValue.serverTimestamp(),
    });
  }

  Future<List<Map<String, dynamic>>> getUserSessions() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return [];

    final snapshot =
        await FirebaseFirestore.instance
            .collection('users')
            .doc(user.uid)
            .collection('sessions')
            .orderBy('created_at', descending: true)
            .get();

    return snapshot.docs
        .map(
          (doc) => {
            'id': doc.id,
            'title':
                doc.data().containsKey('title') ? doc['title'] : 'Untitled',
          },
        )
        .toList();
  }

  Future<List<Map<String, String>>> loadMessagesForSession(
    String sessionId,
  ) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return [];

    final snapshot =
        await FirebaseFirestore.instance
            .collection('users')
            .doc(user.uid)
            .collection('sessions')
            .doc(sessionId)
            .collection('messages')
            .orderBy('timestamp')
            .get();

    return snapshot.docs
    .where((doc) {
      final data = doc.data();
      return data.containsKey('role') && 
             data.containsKey('content') &&
             data['role'] != null && 
             data['content'] != null;
    })
    .map((doc) {
      final data = doc.data();
      final role = data['role']?.toString() ?? 'unknown';
      final content = data['content']?.toString() ?? '';
      return {role: content};
    })
    .toList();
  }
}
