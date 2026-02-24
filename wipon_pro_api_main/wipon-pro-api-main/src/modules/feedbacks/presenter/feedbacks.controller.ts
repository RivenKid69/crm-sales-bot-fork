import { Body, Controller, Post, UseGuards, UseInterceptors } from '@nestjs/common';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { PostFeedbackDto } from '../dto/post-feedback.dto';
import { User } from '../../../common/decorators/user.decorator';
import { FeedbacksService } from '../domain/feedbacks.service';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBody, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('feedback')
@UseInterceptors(TransformInterceptor)
@UseGuards(AuthGuard)
@ApiTags('feedback')
export class FeedbacksController {
  constructor(private readonly feedbacksService: FeedbacksService) {}

  @Post()
  @ApiOperation({
    summary: 'Post feedback',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  @ApiBody({ type: PostFeedbackDto })
  async postFeedback(@Body() postFeedbackDto: PostFeedbackDto, @User() user: UserDao) {
    return await this.feedbacksService.postFeedback(postFeedbackDto, user);
  }
}
