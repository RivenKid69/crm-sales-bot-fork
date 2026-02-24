import { Injectable } from '@nestjs/common';
import * as admin from 'firebase-admin';
import { MessagingPayload } from 'firebase-admin/lib/messaging/messaging-api';

@Injectable()
export class FcmService {
  async sendNotification(token: string, payload: MessagingPayload) {
    return await admin.messaging().sendToDevice(token, payload);
  }
}
