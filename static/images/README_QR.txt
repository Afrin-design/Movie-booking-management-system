HOW TO ADD YOUR OWN UPI QR CODE
================================

1. Open your UPI app (PhonePe / GPay / Paytm / any bank app)
2. Go to "Receive Money" or "My QR Code"  
3. Take a screenshot / save that QR image
4. Rename the image file to:  upi_qr.png
5. Copy it to this folder:    static/images/upi_qr.png
6. Restart the Flask app

That's it! The payment page will automatically show YOUR QR code.

If the file is missing, the page falls back to a generated QR automatically.
