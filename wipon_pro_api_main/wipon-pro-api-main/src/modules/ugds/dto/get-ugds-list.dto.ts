import { IsOptional, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class GetUgdsListDto {
  @IsOptional()
  @IsString({
    message: 'The dgd id must be a string',
  })
  @ApiProperty({
    type: String,
    required: false,
    description: 'Filtering ugd with dgd_id',
  })
  dgd_id: string;
}
