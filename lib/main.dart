// lib/main.dart
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'chat_service.dart';
import 'package:flutter/services.dart';
import 'dart:ui'; // Required for BackdropFilter
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'firebase_options.dart'; // auto-generated
import 'package:cloud_firestore/cloud_firestore.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'StudyBuddy',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(scaffoldBackgroundColor: Colors.white),
      home: SignInPage(),
    );
  }
}

class SignInPage extends StatefulWidget {
  @override
  _SignInPageState createState() => _SignInPageState();
}

class _SignInPageState extends State<SignInPage> {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();

  void _showSignUpDialog() {
    final _nameCtrl = TextEditingController();
    final _surnameCtrl = TextEditingController();
    final _email2Ctrl = TextEditingController();
    final _pass2Ctrl = TextEditingController();
    final _confirmCtrl = TextEditingController();

    showDialog(
      context: context,
      builder:
          (ctx) => AlertDialog(
            backgroundColor: Colors.white,
            title: Text(
              'Sign Up',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildField(_nameCtrl, 'Name'),
                  SizedBox(height: 16),
                  _buildField(_surnameCtrl, 'Surname'),
                  SizedBox(height: 16),
                  _buildField(_email2Ctrl, 'Email'),
                  SizedBox(height: 16),
                  _buildField(_pass2Ctrl, 'Password', obscure: true),
                  SizedBox(height: 16),
                  _buildField(_confirmCtrl, 'Confirm Password', obscure: true),
                ],
              ),
            ),
            actions: [
              TextButton(
                style: TextButton.styleFrom(foregroundColor: Colors.black),
                onPressed: () async {
                  final email = _email2Ctrl.text.trim();
                  final pass = _pass2Ctrl.text.trim();
                  final confirm = _confirmCtrl.text.trim();

                  if (email.isEmpty ||
                      pass.isEmpty ||
                      confirm.isEmpty ||
                      pass != confirm) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          'Please fill all fields and confirm password.',
                        ),
                      ),
                    );
                    return;
                  }

                  try {
                    print("Creating user...");
                    final userCredential = await _auth
                        .createUserWithEmailAndPassword(
                          email: email,
                          password: pass,
                        );

                    final user = userCredential.user;
                    print("User created: $user");

                    if (user != null) {
                      print("Saving to Firestore...");
                      await FirebaseFirestore.instance
                          .collection('users')
                          .doc(user.uid)
                          .set({
                            'name': _nameCtrl.text.trim(),
                            'surname': _surnameCtrl.text.trim(),
                            'email': user.email,
                            'created_at': FieldValue.serverTimestamp(),
                          });

                      print("Saved to Firestore. Navigating...");
                      Navigator.of(ctx).pop();
                      Navigator.of(context).pushReplacement(
                        MaterialPageRoute(
                          builder: (_) => ChatHomePage(user: user),
                        ),
                      );
                    }
                  } catch (e, stackTrace) {
                    print("Sign-up failed: $e");
                    print(stackTrace);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Sign-up failed: ${e.toString()}'),
                      ),
                    );
                  }
                },

                child: Text('Register'),
              ),
              TextButton(
                style: TextButton.styleFrom(foregroundColor: Colors.black54),
                onPressed: () => Navigator.of(ctx).pop(),
                child: Text('Cancel'),
              ),
            ],
          ),
    );
  }

  void _signIn() async {
    final email = _emailCtrl.text.trim();
    final password = _passCtrl.text.trim();

    if (email.isEmpty || password.isEmpty) {
      print("Email or password is empty");
      return;
    }

    try {
      final userCredential = await _auth.signInWithEmailAndPassword(
        email: email,
        password: password,
      );

      final user = userCredential.user;
      print("User: $user");

      if (user != null) {
        // ✅ Check if user profile exists in Firestore
        final docRef = FirebaseFirestore.instance
            .collection('users')
            .doc(user.uid);
        final docSnap = await docRef.get();

        if (!docSnap.exists) {
          // 🛠️ Create a minimal profile for this user
          await docRef.set({
            'email': user.email,
            'created_at': FieldValue.serverTimestamp(),
            'name': '', // Optional default
            'surname': '', // Optional default
          });
          print("User profile created in Firestore.");
        } else {
          print("User profile already exists.");
        }

        final idTokenResult = await user.getIdTokenResult();
final isAdmin = idTokenResult.claims?['admin'] == true;

if (isAdmin) {
  Navigator.of(context).pushReplacement(
    MaterialPageRoute(builder: (_) => AdminPage()),
  );
} else {
  Navigator.of(context).pushReplacement(
    MaterialPageRoute(builder: (_) => ChatHomePage(user: user)),
  );
}
      } else {
        print("Login succeeded but user is null.");
      }
    } catch (e) {
      print("Login failed: $e");
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Login failed: ${e.toString()}')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      resizeToAvoidBottomInset: false,
      body: Center(
        child: Container(
          width: 350,
          padding: EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'StudyBuddy',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  color: Colors.black,
                ),
              ),
              SizedBox(height: 48),
              _buildField(_emailCtrl, 'Email'),
              SizedBox(height: 24),
              _buildField(_passCtrl, 'Password', obscure: true),
              SizedBox(height: 48),
              ElevatedButton(
                onPressed: _signIn,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.black,
                  minimumSize: Size(double.infinity, 48),
                ),
                child: Text(
                  'Sign In',
                  style: TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
              SizedBox(height: 16),
              TextButton(
                style: TextButton.styleFrom(foregroundColor: Colors.black54),
                onPressed: _showSignUpDialog,
                child: Text('Create an account'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildField(
    TextEditingController c,
    String hint, {
    bool obscure = false,
  }) {
    return TextField(
      controller: c,
      obscureText: obscure,
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: TextStyle(color: Colors.black54),
        border: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.black54),
        ),
        focusedBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.black),
        ),
      ),
    );
  }
}



class AdminPage extends StatefulWidget {
  @override
  _AdminPageState createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage> {
  int _totalUsers = 0;
  int _todayUsers = 0;
  List<Map<String, dynamic>> _users = [];
  bool _showUserList = false;
  List<Map<String, dynamic>> _userSessions = [];
  String? _selectedUserEmail;

  @override
  void initState() {
    super.initState();
    _fetchUserStats();
  }

  Future<void> _fetchUserStats() async {
    final snapshot = await FirebaseFirestore.instance.collection('users').get();
    final today = DateTime.now();
    final todayUsers = snapshot.docs.where((doc) {
      final createdAt = doc['created_at']?.toDate();
      return createdAt != null &&
          createdAt.year == today.year &&
          createdAt.month == today.month &&
          createdAt.day == today.day;
    }).length;

    setState(() {
      _totalUsers = snapshot.size;
      _todayUsers = todayUsers;
      _users = snapshot.docs.map((doc) => {'id': doc.id, 'email': doc['email']}).toList();
    });
  }

  Future<void> _deleteUser(String uid) async {
  final userDoc = FirebaseFirestore.instance.collection('users').doc(uid);
  final sessionsSnapshot = await userDoc.collection('sessions').get();

  // Delete messages under each session
  for (final sessionDoc in sessionsSnapshot.docs) {
    final messagesSnapshot = await sessionDoc.reference.collection('messages').get();
    for (final message in messagesSnapshot.docs) {
      await message.reference.delete();
    }
    await sessionDoc.reference.delete(); // delete the session doc
  }

  // Delete user doc
  await userDoc.delete();

  // Update UI
  setState(() {
    _users.removeWhere((u) => u['id'] == uid);
    if (_selectedUserEmail == uid) {
      _selectedUserEmail = null;
      _userSessions.clear();
    }
  });
}

  Future<void> _fetchSessions(String uid, String email) async {
    final snapshot = await FirebaseFirestore.instance.collection('users').doc(uid).collection('sessions').get();
    setState(() {
      _userSessions = snapshot.docs.map((doc) => {
        'id': doc.id,
        'title': doc.data()['title'] ?? 'Untitled'
      }).toList();
      _selectedUserEmail = email;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Admin Dashboard'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: () async {
              await FirebaseAuth.instance.signOut();
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => SignInPage()),
              );
            },
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          children: [
            Text('USERS', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            SizedBox(height: 12),
            Container(
              padding: EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.grey.shade200,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.black12),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  Column(
                    children: [
                      Text('Users', style: TextStyle(fontWeight: FontWeight.bold)),
                      SizedBox(height: 4),
                      Text('$_totalUsers'),
                    ],
                  ),
                  Column(
                    children: [
                      Text('Signed up', style: TextStyle(fontWeight: FontWeight.bold)),
                      SizedBox(height: 4),
                      Text('$_todayUsers'),
                    ],
                  ),
                ],
              ),
            ),
            SizedBox(height: 20),
            ElevatedButton(
              onPressed: () => setState(() => _showUserList = !_showUserList),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.grey.shade300,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
              ),
              child: Text('Manage users', style: TextStyle(color: Colors.black)),
            ),
            if (_showUserList) ...[
              SizedBox(height: 20),
              Flexible(
                child: ListView(
                  children: _users.map((u) => ListTile(
                    title: Text(u['email']),
                    trailing: IconButton(
                      icon: Icon(Icons.delete, color: Colors.red),
                      onPressed: () => _deleteUser(u['id']),
                    ),
                    onTap: () => _fetchSessions(u['id'], u['email']),
                  )).toList(),
                ),
              ),
              if (_selectedUserEmail != null) ...[
                SizedBox(height: 20),
                Text('Sessions for $_selectedUserEmail', style: TextStyle(fontWeight: FontWeight.bold)),
                SizedBox(height: 10),
                Flexible(
                  child: ListView(
                    children: _userSessions.map((s) => ListTile(
                      title: Text(s['title']),
                      subtitle: Text(s['id']),
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => AdminChatView(
                            userId: _users.firstWhere((u) => u['email'] == _selectedUserEmail)['id'],
                            sessionId: s['id'],
                          ),
                        ),
                      ),
                    )).toList(),
                  ),
                ),
              ]
            ]
          ],
        ),
      ),
    );
  }
}

class AdminChatView extends StatelessWidget {
  final String userId;
  final String sessionId;

  AdminChatView({required this.userId, required this.sessionId});

  Future<List<Map<String, dynamic>>> _fetchMessages() async {
    final snapshot = await FirebaseFirestore.instance
        .collection('users')
        .doc(userId)
        .collection('sessions')
        .doc(sessionId)
        .collection('messages')
        .orderBy('timestamp')
        .get();

    return snapshot.docs.map((doc) => doc.data()).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text("Chat View"),
        actions: [
          IconButton(
            icon: Icon(Icons.exit_to_app),
            onPressed: () => Navigator.pop(context),
          )
        ],
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _fetchMessages(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return Center(child: CircularProgressIndicator());
          }
          if (!snapshot.hasData || snapshot.data!.isEmpty) {
            return Center(child: Text("No messages found."));
          }
          final messages = snapshot.data!;
          return ListView.builder(
            padding: EdgeInsets.all(16),
            itemCount: messages.length,
            itemBuilder: (context, index) {
              final msg = messages[index];
              return ListTile(
                title: Text('${msg['role']}:'),
                subtitle: Text(msg['content']),
              );
            },
          );
        },
      ),
    );
  }
}



class ProfilePage extends StatefulWidget {
  final String name;
  final String email;

  ProfilePage({required this.name, required this.email});

  @override
  _ProfilePageState createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  final _nameCtrl = TextEditingController();
  final _surnameCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _passCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadUserProfile();
  }

  Future<void> _loadUserProfile() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user != null) {
      final doc =
          await FirebaseFirestore.instance
              .collection('users')
              .doc(user.uid)
              .get();
      if (doc.exists) {
        setState(() {
          _nameCtrl.text = doc['name'] ?? '';
          _surnameCtrl.text = doc['surname'] ?? '';
          _phoneCtrl.text = doc['phone'] ?? '';
        });
      }
    }
  }

  void _saveChanges() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user != null) {
      try {
        await FirebaseFirestore.instance
            .collection('users')
            .doc(user.uid)
            .update({
              'name': _nameCtrl.text.trim(),
              'surname': _surnameCtrl.text.trim(),
              'phone': _phoneCtrl.text.trim(),
            });

        if (_passCtrl.text.isNotEmpty) {
          await user.updatePassword(_passCtrl.text);
        }

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Profile updated successfully!')),
        );
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Update failed: ${e.toString()}')),
        );
      }
    }
  }

  @override
  @override
Widget build(BuildContext context) {
  return Scaffold(
    appBar: AppBar(
      title: Text('Profile'),
      backgroundColor: Colors.white,
      foregroundColor: Colors.black,
      elevation: 0,
    ),
    body: SingleChildScrollView(
      padding: EdgeInsets.all(16),
      child: Column(
        children: [
          // Profile Avatar + Name
          Column(
            children: [
              CircleAvatar(
                radius: 40,
                backgroundImage: AssetImage('assets/user.jpg'), // Replace with user photo if available
              ),
              SizedBox(height: 12),
              Text(
                '${_nameCtrl.text} ${_surnameCtrl.text}',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              Text(
                widget.email,
                style: TextStyle(color: Colors.grey[700]),
              ),
            ],
          ),
          SizedBox(height: 24),

          // Editable fields inside cards
          _buildEditableField(
            icon: Icons.person,
            label: 'First Name',
            controller: _nameCtrl,
          ),
          _buildEditableField(
            icon: Icons.person_outline,
            label: 'Last Name',
            controller: _surnameCtrl,
          ),
          _buildEditableField(
            icon: Icons.phone,
            label: 'Phone (optional)',
            controller: _phoneCtrl,
            inputType: TextInputType.phone,
          ),
          _buildEditableField(
            icon: Icons.lock,
            label: 'New Password',
            controller: _passCtrl,
            isPassword: true,
          ),
          SizedBox(height: 24),

          ElevatedButton.icon(
            onPressed: _saveChanges,
            icon: Icon(Icons.save),
            label: Text('Save Changes'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.black,
              foregroundColor: Colors.white,
              padding: EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}
Widget _buildEditableField({
  required IconData icon,
  required String label,
  required TextEditingController controller,
  TextInputType inputType = TextInputType.text,
  bool isPassword = false,
}) {
  return Padding(
    padding: const EdgeInsets.only(bottom: 16.0),
    child: Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1), // subtle outer shadow
            blurRadius: 8,
            offset: Offset(0, 4), // shadow below the field
          ),
        ],
      ),
      child: TextField(
        controller: controller,
        keyboardType: inputType,
        obscureText: isPassword,
        style: TextStyle(color: Colors.black),
        cursorColor: Colors.black,
        decoration: InputDecoration(
          prefixIcon: Icon(icon, color: Colors.black),
          labelText: label,
          labelStyle: TextStyle(color: Colors.black),
          filled: true,
          fillColor: Colors.white,
          enabledBorder: OutlineInputBorder(
            borderSide: BorderSide.none, // remove border since we use shadow
            borderRadius: BorderRadius.circular(12),
          ),
          focusedBorder: OutlineInputBorder(
            borderSide: BorderSide(color: Colors.black, width: 1.5),
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
    ),
  );
}




}

class ChatHomePage extends StatefulWidget {
  final User user;
  ChatHomePage({required this.user});

  @override
  _ChatHomePageState createState() => _ChatHomePageState();
}

final FocusScopeNode _focusNode = FocusScopeNode();
final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

class _ChatHomePageState extends State<ChatHomePage>
    with WidgetsBindingObserver {
  final ChatService _svc = ChatService();
  List<String> _sessionIds = [];
  List<String> _titles = [];
  int _selected = -1;
  List<Map<String, String>> _msgs = [];
  final _inCtrl = TextEditingController();
  final _scroll = ScrollController();
  bool _loading = true;

  String _displayName = '';
  String _userEmail = '';

  Future<void> _loadUserProfile() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return;

    final doc =
        await FirebaseFirestore.instance
            .collection('users')
            .doc(user.uid)
            .get();
    final data = doc.data();

    if (data != null) {
      setState(() {
        _displayName = '${data['name']} ${data['surname']}';
        _userEmail = data['email'] ?? '';
      });
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this); // Start observing app lifecycle
    _startFresh();
    _loadUserProfile(); // <- here
  }

  Future<void> _startFresh() async {
    final sessions = await _svc.getUserSessions(); // 🔁 Firestore now
    final titles = <String>[];
    String? reusableId;
    final userId = FirebaseAuth.instance.currentUser!.uid;


    for (var s in sessions) {
      final sid = s['id'] as String;
      final hist = await _svc.loadMessagesForSession(sid);

      if (hist.isEmpty && reusableId == null) {
        reusableId = sid;
        titles.add('New Chat');
      } else if (hist.isNotEmpty) {
        final first = hist.firstWhere(
          (m) => m.containsKey('user'),
          orElse: () => {'user': 'New Chat'},
        );
        titles.add(first['user'] ?? 'New Chat');
      } else {
        titles.add('New Chat');
      }
    }

    // Use reusable session or create a new one
    final sid = reusableId ?? await _svc.initSession();
    if (reusableId == null) {
      titles.insert(0, 'New Chat');
    }

    _sessionIds =
        reusableId != null
            ? sessions.map((s) => s['id'] as String).toList()
            : [sid, ...sessions.map((s) => s['id'] as String)];

    _titles = titles;
    _svc.sessionId = sid;

    try {
      await http.post(Uri.parse("https://dec0-194-27-149-159.ngrok-free.app/users/$userId/sessions/$sid/load"));
print("✅ Session loaded on backend: $sid");

    } catch (e) {
      print("❌ Failed to load session on backend: $e");
    }

    _selected = _sessionIds.indexOf(sid);
    _msgs.clear();
    _loading = false;

    // 🔧 Deduplication
    final uniqueIds = <String>{};
    final dedupedSessionIds = <String>[];
    final dedupedTitles = <String>[];

    print('🧭 Active sessionId: ${_svc.sessionId}');
    for (int i = 0; i < _sessionIds.length; i++) {
      final id = _sessionIds[i];
      if (uniqueIds.add(id)) {
        dedupedSessionIds.add(id);
        dedupedTitles.add(_titles[i]);
      }
    }

    // ✅ Set state
    setState(() {
      _sessionIds = dedupedSessionIds;
      _titles = dedupedTitles;
      _svc.sessionId = sid;
      _selected = _sessionIds.indexOf(sid);
      _msgs.clear();
      _loading = false;
    });
  }

  @override
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(
      this,
    ); // Stop observing when page destroyed
    _terminateCurrentSession(); // Try save chat
    _inCtrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) async {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached) {
      await _terminateCurrentSession(); // Save the current session
    } else if (state == AppLifecycleState.resumed) {
      // When the app resumes from background
      if (_selected >= 0 && _sessionIds.isNotEmpty) {
        final sid = _sessionIds[_selected];
        print('🧭 Active sessionId: ${_svc.sessionId}');
        _svc.sessionId = sid; // make sure service has correct session id
        try {
          final user = FirebaseAuth.instance.currentUser;
          final userId = user?.uid ?? '';
          final sessionId = _svc.sessionId ?? '';
          await http.post(
            Uri.parse(
              'https://dec0-194-27-149-159.ngrok-free.app/users/$userId/sessions/$sessionId/load',
            ),
          );
          print("✅ Session loaded on backend: $sid");
        } catch (e) {
          print('❌ Failed to load session: $e');
        }
      }
    }
  }

  Future<void> _terminateCurrentSession() async {
    if (_selected >= 0 && _sessionIds.isNotEmpty) {
      // Check if user actually sent a message
      final hasRealUserMessage = _msgs.any((msg) => msg.keys.contains('user'));

      if (!hasRealUserMessage) {
        print('Skipping termination: No real user message in current session.');
        return; // If no user messages, don't terminate
      }

      try {
        final user = FirebaseAuth.instance.currentUser;
        final userId = user?.uid ?? '';
        final sessionId = _svc.sessionId ?? '';
        await http.post(
          Uri.parse(
            'https://dec0-194-27-149-159.ngrok-free.app/users/$userId/sessions/$sessionId/load',
          ),
        );
      } catch (e) {
        print('Failed to reload session on resume: $e');
      }
    }
  }

  Future<void> _initAllSessions() async {
    final ids = await _svc.listSessions();
    if (ids.isEmpty) {
      final sid = await _svc.initSession();
      setState(() {
        _sessionIds = [sid];
        _titles = ['New Chat'];
        _selected = 0;
        _msgs.clear();
        _loading = false;
      });
      return;
    }
    final titles = <String>[];
    for (var sid in ids) {
      final hist = await _svc.fetchMessagesForSession(sid);
      if (hist.isEmpty) {
        titles.add('New Chat');
      } else {
        final first = hist.firstWhere(
          (m) => m.role == 'user',
          orElse: () => Message(role: 'user', content: 'New Chat'),
        );
        titles.add(first.content);
      }
    }
    setState(() {
      _sessionIds = ids;
      _titles = titles;
      _selected = 0;
      _loading = false;
    });
    if (_sessionIds.isNotEmpty) {
      await _switch(0);
    }
  }

  Future<void> _newChat() async {
    await _terminateCurrentSession();

    final sid = await _svc.initSession(); // Firestore handles creation

    // Load session on backend (still needed)
    try {
      final user = FirebaseAuth.instance.currentUser;
      final userId = user?.uid ?? '';
      final sessionId = _svc.sessionId ?? '';
      await http.post(
        Uri.parse(
          'https://dec0-194-27-149-159.ngrok-free.app/users/$userId/sessions/$sessionId/load',
        ),
      );
      print("✅ Session loaded on backend: $sid");
    } catch (e) {
      print('❌ Failed to load session: $e');
    }

    setState(() {
      _sessionIds.insert(0, sid);
      _titles.insert(
        0,
        'New Chat',
      ); // Actual title saved after user sends message
      _selected = 0;
      _msgs.clear();
    });
  }

  Future<void> _switch(int i) async {
    // Step 1: Terminate current session
    await _terminateCurrentSession();

    // Step 2: Set and load the new session on the backend
    final sid = _sessionIds[i];
    _svc.sessionId = sid;
    final user = FirebaseAuth.instance.currentUser;
    final userId = user?.uid ?? '';
    final sessionId = _svc.sessionId ?? '';

    try {
      final user = FirebaseAuth.instance.currentUser;
      final userId = user?.uid ?? '';
      final sessionId = _svc.sessionId ?? '';
      await http.post(
        Uri.parse(
          'https://dec0-194-27-149-159.ngrok-free.app/users/$userId/sessions/$sessionId/load',
        ),
      );
      print("✅ Session loaded on backend: $sid");
    } catch (e) {
      print('❌ Failed to load session: $e');
    }

    // Step 3: Fetch chat history from Firestore
    final hist = await _svc.loadMessagesForSession(
      sid,
    ); // 🔁 REPLACED backend API call

    setState(() {
      _selected = i;
      if (hist.isEmpty) {
        _msgs = [
          {'ai': 'Start the conversation by saying hi!'},
        ];
      } else {
        _msgs = hist;
      }
    });
  }

  Future<void> _send() async {
    if (_selected < 0) {
      await _newChat();
    }

    final t = _inCtrl.text.trim();
    if (t.isEmpty) return;

    final user = FirebaseAuth.instance.currentUser;
    if (user == null || _svc.sessionId == null) {
      setState(
        () => _msgs.add({
          'ai': 'Error: User not authenticated or session not initialized',
        }),
      );
      return;
    }

    setState(() {
      _msgs.add({'user': t});
      if (_titles[_selected] == 'New Chat') {
        _titles[_selected] = t;
      }
    });
    _inCtrl.clear();

    try {
      final ai = await _svc.sendMessage(user.uid, _svc.sessionId!, t);
      setState(() => _msgs.add({'ai': ai.content}));
    } catch (e) {
      setState(() => _msgs.add({'ai': 'Error: $e'}));
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          0, // scroll to bottom since list is reversed
          duration: Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext ctx) {
    if (_loading) {
      return Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final inset = MediaQuery.of(ctx).viewInsets.bottom;
    const ibh = 56.0;

    return Scaffold(
      key: _scaffoldKey,
      resizeToAvoidBottomInset: true,
      appBar: PreferredSize(
        preferredSize: Size.fromHeight(kToolbarHeight),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(
              1.0,
            ), // Change to 1.0 for solid white
            boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 0)],
          ),
          child: SafeArea(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                IconButton(
                  icon: Icon(Icons.menu, color: Colors.black),
                  onPressed: () {
                    _focusNode.unfocus();
                    _scaffoldKey.currentState?.openDrawer();
                  },
                ),
                Text(
                  'StudyBuddy',
                  style: TextStyle(
                    color: Colors.black,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(width: 48), // to balance the menu icon
              ],
            ),
          ),
        ),
      ),

      drawer: Drawer(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(height: MediaQuery.of(ctx).padding.top + 8),

            // Title
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Chats',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  IconButton(icon: Icon(Icons.add), onPressed: _newChat),
                ],
              ),
            ),

            // All chats
            Expanded(
              child: ListView.builder(
                padding: EdgeInsets.zero,
                itemCount: _sessionIds.length,
                itemBuilder:
                    (c, i) => ListTile(
                      title: Text(_titles[i], style: TextStyle(fontSize: 14)),
                      selected: i == _selected,
                      selectedTileColor: Colors.grey.shade200,
                      onTap: () => _switch(i),
                      contentPadding: EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 4,
                      ),
                    ),
              ),
            ),

            // Slight space
            SizedBox(height: 10),

            // Profile Tile
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: ListTile(
                leading: CircleAvatar(
                  backgroundImage: AssetImage(
                    'assets/user.jpg',
                  ), // Make sure the image exists
                ),
                title: Text(_displayName.isNotEmpty ? _displayName : '...'),
                subtitle: Text('View Profile'),
                onTap: () async {
                  _focusNode.unfocus();
                  showModalBottomSheet(
                    context: context,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.vertical(
                        top: Radius.circular(16),
                      ),
                    ),
                    builder:
                        (_) => Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ListTile(
                              leading: Icon(Icons.person),
                              title: Text('View Profile'),
                              onTap: () async{
                                Navigator.of(context).pop();
                                 await Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder:
                                        (_) => ProfilePage(
                                          name: _displayName,
                                          email: _userEmail,
                                        ),
                                  ),
                                );
                                await _loadUserProfile();
                              },
                            ),
                            ListTile(
                              leading: Icon(Icons.logout),
                              title: Text('Sign Out'),
                              onTap: () {
                                Navigator.of(context).pop();
                                Navigator.of(context).pushReplacement(
                                  MaterialPageRoute(
                                    builder: (_) => SignInPage(),
                                  ),
                                );
                              },
                            ),
                          ],
                        ),
                  );
                },
              ),
            ),

            SizedBox(height: 12), // (optional) Extra breathing room at bottom
          ],
        ),
      ),

      body: GestureDetector(
        onTap: () => _focusNode.unfocus(),
        child: SafeArea(
          child: FocusScope(
            node: _focusNode,
            child: Column(
              children: [
                // message list
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      return SingleChildScrollView(
                        reverse: true,
                        controller: _scroll,
                        padding: EdgeInsets.symmetric(horizontal: 16),
                        child: ConstrainedBox(
                          constraints: BoxConstraints(
                            minHeight: constraints.maxHeight,
                          ),
                          child: IntrinsicHeight(
                            child: Column(
                              children: [
                                if (_msgs.isEmpty)
                                  Expanded(
                                    child: Center(
                                      child: Text(
                                        'No messages yet.\nStart a new conversation!',
                                        textAlign: TextAlign.center,
                                        style: TextStyle(
                                          fontSize: 18,
                                          color: Colors.black54,
                                        ),
                                      ),
                                    ),
                                  )
                                else
                                  ..._msgs.map((m) {
                                    final isUser = m.keys.first == 'user';
                                    return Align(
                                      alignment:
                                          isUser
                                              ? Alignment.centerRight
                                              : Alignment.centerLeft,
                                      child: Container(
                                        margin: EdgeInsets.symmetric(
                                          vertical: 4,
                                        ),
                                        padding: EdgeInsets.all(12),
                                        decoration: BoxDecoration(
                                          color:
                                              isUser
                                                  ? Colors.blueAccent.shade100
                                                  : Colors.grey.shade300,
                                          borderRadius: BorderRadius.only(
                                            topLeft: Radius.circular(16),
                                            topRight: Radius.circular(16),
                                            bottomLeft:
                                                isUser
                                                    ? Radius.circular(16)
                                                    : Radius.circular(0),
                                            bottomRight:
                                                isUser
                                                    ? Radius.circular(0)
                                                    : Radius.circular(16),
                                          ),
                                        ),
                                        child: Text(
                                          m.values.first,
                                          style: TextStyle(fontSize: 16),
                                        ),
                                      ),
                                    );
                                  }).toList(),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),

                // input bar
                Container(
                  padding: EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(16),
                      topRight: Radius.circular(16),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black12,
                        blurRadius: 4,
                        offset: Offset(0, -2),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _inCtrl,
                          maxLines: null,
                          decoration: InputDecoration(
                            hintText: 'Type a message',
                            hintStyle: TextStyle(color: Colors.black45),
                            border: InputBorder.none,
                          ),
                          onSubmitted: (_) => _send(),
                        ),
                      ),
                      IconButton(
                        icon: Icon(Icons.send, color: Colors.black),
                        onPressed: _send,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
