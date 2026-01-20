import os
import requests
import logging

logger = logging.getLogger(__name__)

class SMTP2GoSimple:
    """Servicio SMTP2Go simplificado"""
    
    def __init__(self):
        self.api_key = os.environ.get("SMTP2GO_API_KEY", "test_key")
        self.sender = os.environ.get("SMTP2GO_SENDER", "test@example.com")
        self.enabled = bool(self.api_key and self.sender != "test@example.com")
        
    def enviar_verificacion(self, usuario):
        """Envía correo de verificación simplificado"""
        
        # Si no está configurado SMTP2Go, solo loguear
        if not self.enabled:
            logger.info(f"📧 Email simulado para: {usuario.email}")
            return {"success": True, "simulated": True}
        
        # Preparar el correo
        subject = f"✅ Cuenta verificada - {usuario.username}"
        
        # Texto simple
        text_body = f"""
Hola {usuario.username},

Tu cuenta ha sido verificada exitosamente.

Saldo actual: ${usuario.saldo:,} COP

Ahora puedes acceder a todas las funciones.

Saludos,
El equipo
"""
        
        # HTML simple
        html_body = f"""
<!DOCTYPE html>
<html>
<body>
<h2>Cuenta Verificada</h2>
<p>Hola <strong>{usuario.username}</strong>,</p>
<p>Tu cuenta ha sido verificada exitosamente.</p>
<p><strong>Saldo:</strong> ${usuario.saldo:,} COP</p>
<p>Ahora puedes acceder a todas las funciones.</p>
<hr>
<p>Saludos,<br>El equipo</p>
</body>
</html>
"""
        
        # Llamar a la API de SMTP2Go
        url = "https://api.smtp2go.com/v3/email/send"
        payload = {
            "api_key": self.api_key,
            "sender": self.sender,
            "to": [usuario.email],
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            
            if response.status_code == 200 and data.get("data", {}).get("succeeded") == 1:
                logger.info(f"✅ Email enviado a: {usuario.email}")
                return {"success": True, "email_id": data.get("data", {}).get("email_id")}
            else:
                logger.error(f"❌ Error SMTP2Go: {data}")
                return {"success": False, "error": data.get("error", "Unknown error")}
                
        except Exception as e:
            logger.error(f"⚠️ Error enviando email: {str(e)}")
            return {"success": False, "error": str(e)}

# Instancia global
smtp2go = SMTP2GoSimple()