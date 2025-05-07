// lib/main.dart
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'chat_service.dart';
import 'package:flutter/services.dart';
import 'dart:ui'; // Required for BackdropFilter

void main() {
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
                onPressed: () => Navigator.of(ctx).pop(),
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

  void _signIn() {
    Navigator.of(
      context,
    ).pushReplacement(MaterialPageRoute(builder: (_) => ChatHomePage()));
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
              TextButton(
                onPressed: () {
                  Navigator.of(
                    context,
                  ).push(MaterialPageRoute(builder: (_) => AdminPage()));
                },
                child: Text(
                  'Admin Login',
                  style: TextStyle(
                    color: Colors.black54,
                    fontWeight: FontWeight.bold,
                  ),
                ),
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

class AdminPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Admin Dashboard'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: Center(
        child: Text(
          'Welcome to the Admin Panel',
          style: TextStyle(fontSize: 18),
        ),
      ),
    );
  }
}

class ProfilePage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Profile')),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 40,
              backgroundImage: AssetImage('assets/user.jpg'),
            ),
            SizedBox(height: 12),
            Text(
              'John Doe',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            Text('john@example.com'),
          ],
        ),
      ),
    );
  }
}

class ChatHomePage extends StatefulWidget {
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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this); // Start observing app lifecycle
    _startFresh();
  }

  Future<void> _startFresh() async {
    final oldIds = await _svc.listSessions();
    final titles = <String>[];
    String? reusableId;

    for (var osid in oldIds) {
      final hist = await _svc.fetchMessagesForSession(osid);
      if (hist.isEmpty && reusableId == null) {
        reusableId = osid; // Reuse first empty session
        titles.add('New Chat');
      } else if (hist.isNotEmpty) {
        final first = hist.firstWhere(
          (m) => m.role == 'user',
          orElse: () => Message(role: 'user', content: 'New Chat'),
        );
        titles.add(first.content);
      } else {
        titles.add('New Chat');
      }
    }

    // Use existing empty session or create new one
    final sid = reusableId ?? await _svc.initSession();
    if (reusableId == null) {
      titles.insert(0, 'New Chat');
    }

    _sessionIds = reusableId != null ? oldIds : [sid, ...oldIds];
    _titles = titles;
    _svc.sessionId = sid;
    _selected = _sessionIds.indexOf(sid);
    _msgs.clear();
    _loading = false;

    // 🔧 Deduplicate before setting state
    final uniqueIds = <String>{};
    final dedupedSessionIds = <String>[];
    final dedupedTitles = <String>[];

    for (int i = 0; i < _sessionIds.length; i++) {
      final id = _sessionIds[i];
      if (uniqueIds.add(id)) {
        dedupedSessionIds.add(id);
        dedupedTitles.add(_titles[i]);
      }
    }

    // ✅ Set state with cleaned-up session list
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
        _svc.sessionId = sid; // make sure service has correct session id
        try {
          await http.post(
            Uri.parse('http://127.0.0.1:8000/sessions/$sid/load'),
          );
          //await http.post(Uri.parse('http://172.20.10.2:8000/sessions/$sid/load'));
        } catch (e) {
          print('Failed to reload session on resume: $e');
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
        await http.post(
          Uri.parse(
            'http://127.0.0.1:8000/sessions/${_sessionIds[_selected]}/terminate',
            //'http://172.20.10.2:8000/sessions/${_sessionIds[_selected]}/terminate',
          ),
        );
      } catch (e) {
        print('Failed to terminate session: $e');
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
    final sid = await _svc.initSession();
    setState(() {
      _sessionIds.insert(0, sid);
      _titles.insert(0, 'New Chat');
      _selected = 0;
      _msgs.clear();
    });
  }

  Future<void> _switch(int i) async {
    // Step 1: Terminate current session
    await _terminateCurrentSession();

    final sid = _sessionIds[i];
    _svc.sessionId = sid;

    // Try to load (reactivate) the session first
    try {
      await http.post(Uri.parse('http://127.0.0.1:8000/sessions/$sid/load'));
      //await http.post(Uri.parse('http://172.20.10.2:8000/sessions/$sid/load'));
    } catch (e) {
      print('Failed to load session: $e');
      // It's okay, maybe already active
    }

    // Step 3: Fetch chat history
    final hist = await _svc.fetchMessagesForSession(sid);

    setState(() {
      _selected = i;
      if (hist.isEmpty) {
        _msgs = [
          {'ai': 'Start the conversation by saying hi!'},
        ];
      } else {
        _msgs = hist.map((m) => {m.role: m.content}).toList();
      }
    });
  }

  Future<void> _send() async {
    if (_selected < 0) {
      await _newChat();
    }
    final t = _inCtrl.text.trim();
    if (t.isEmpty) return;
    setState(() {
      _msgs.add({'user': t});
      if (_titles[_selected] == 'New Chat') {
        _titles[_selected] = t;
      }
    });
    _inCtrl.clear();
    try {
      final ai = await _svc.sendMessage(t);
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
                title: Text('John Doe'),
                subtitle: Text('View Profile'),
                onTap: () {
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
                              onTap: () {
                                Navigator.of(context).pop();
                                Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) => ProfilePage(),
                                  ),
                                );
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
