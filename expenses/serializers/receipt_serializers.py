from rest_framework import serializers

from expenses.models import Receipt

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

# Statuses with a result: the extracted fields and warnings are only returned once ready.
READY_STATUSES = {Receipt.Status.EXTRACTED, Receipt.Status.FAILED, Receipt.Status.CONFIRMED}


class ReceiptUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()

    def validate_image(self, image):
        if image.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError("The image must be 10 MB or smaller.")
        return image


class QueuedReceiptSerializer(serializers.Serializer):
    """Output of receipt_service.queue_receipt: the new receipt's id and status, and the usage."""

    id = serializers.IntegerField(source="receipt.pk")
    status = serializers.CharField(source="receipt.status")
    usage = serializers.DictField()


class ReceiptStatusSerializer(serializers.ModelSerializer):
    """A receipt for the upload page to poll. raw_text, extracted, warnings and
    confidence are null until the worker has finished with it."""

    class Meta:
        model = Receipt
        fields = ["id", "status", "uploaded_at", "raw_text", "extracted", "warnings", "confidence"]
        read_only_fields = fields

    confidence = serializers.FloatField(source="ocr_confidence")

    def to_representation(self, receipt):
        data = super().to_representation(receipt)
        if receipt.status not in READY_STATUSES:
            data.update(raw_text=None, extracted=None, warnings=None, confidence=None)
        return data
