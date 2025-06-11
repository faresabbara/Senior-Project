const admin = require("firebase-admin");
const serviceAccount = require("./firebase-key.json");

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});

const email = "h1@gmail.com"; // CHANGE THIS TO YOUR ADMIN'S EMAIL

admin.auth().getUserByEmail(email)
  .then(user => {
    return admin.auth().setCustomUserClaims(user.uid, { admin: true });
  })
  .then(() => {
    console.log("Custom claim 'admin: true' set successfully!");
    process.exit(0);
  })
  .catch(error => {
    console.error("Error setting custom claim:", error);
    process.exit(1);
  });