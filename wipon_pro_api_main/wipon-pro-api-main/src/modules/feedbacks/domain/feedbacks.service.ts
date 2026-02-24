import { Injectable } from '@nestjs/common';
import { PostFeedbackDto } from '../dto/post-feedback.dto';
import { InjectRepository } from '@nestjs/typeorm';
import { FeedbacksRepository } from '../data/feedbacks.repository';
import { subMinutesFromNow } from '../../../common/helpers/datetime';
import { saveBase64ImageExif } from '../../../common/helpers/save-image';
import appConfig from '../../../config/app.config';
import { DoomguyService } from '../../../common/services/doomguy/doomguy.service';
import { UserDao } from '../../../common/dao/user.dao';

@Injectable()
export class FeedbacksService {
  private readonly Base64_SAVE_SUBDIRECTORY = 'feedback_messages';
  constructor(
    @InjectRepository(FeedbacksRepository) private readonly feedbacksRepo: FeedbacksRepository,
    private readonly doomguy: DoomguyService,
  ) {}

  async postFeedback(postFeedback: PostFeedbackDto, user: UserDao) {
    const name = this.strip_tags(postFeedback.name);
    const phoneNumber = postFeedback.phone_number;
    const email = this.strip_tags(postFeedback.email);
    const text = this.htmlEntities(postFeedback.text);
    const appLog = postFeedback.app_log;

    const feedback = await this.feedbacksRepo.count({
      where: {
        user_id: user.id,
        created_at: subMinutesFromNow(5),
        phone_number: phoneNumber,
        email,
        name,
        text,
      },
    });

    if (feedback) {
      return { status: 'success' };
    }

    let stickerUri;
    if (postFeedback.photo) {
      stickerUri = await saveBase64ImageExif(postFeedback.photo, this.Base64_SAVE_SUBDIRECTORY);
    }

    const message = this.feedbacksRepo.create({
      user_id: user.id,
      name,
      phone_number: phoneNumber,
      email,
      text,
      photo: postFeedback.photo,
      app_log: appLog,
      created_at: new Date(),
    });

    await this.feedbacksRepo.save(message);

    const env = appConfig.environment;
    if (env !== 'testing') {
      let pushToken;
      let platform;
      let model;
      if (user.device) {
        const device = user.device;
        pushToken = device.push_token;
        platform = device.platform;
        model = device.model;
      }
      const messageFieldsToSlack = {
        app_version: user.app_version || 'Не указана',
        push_token: pushToken ? pushToken : 'Не указан',
        date:
          message && message.created_at
            ? message.created_at.toLocaleString('ru-RU', { timeZone: 'Asia/Almaty' })
            : 'Не указано',
        platform: `${platform ? platform : 'Платформа не указана'}, ${model ? model : 'Модель не указана'}`,
      };

      await this.doomguy.sendFeedback(messageFieldsToSlack);
    }

    return {
      status: 'success',
    };
  }

  private strip_tags(str: string) {
    if (!str || !str.length) return '';
    return str.replace(/<\/?[^>]+>/gi, '');
  }

  private htmlEntities(str) {
    if (!str || !str.length) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
}
