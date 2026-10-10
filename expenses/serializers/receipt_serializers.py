from rest_framework import serializers

from expenses.models import Receipt

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


class ReceiptUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()

    def validate_image(self, image):
        if image.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError("The image must be 10 MB or smaller.")
        return image


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = ["id", "status", "raw_text", "uploaded_at"]
        read_only_fields = fields


class ProcessedReceiptSerializer(serializers.Serializer):
    """Output of receipt_service.process_receipt: the receipt plus the extracted fields."""

    receipt = ReceiptSerializer()
    # Named "extracted" because "fields" would shadow Serializer.fields.
    extracted = serializers.DictField(source="fields")
    confidence = serializers.FloatField()
